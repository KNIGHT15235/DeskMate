"""Personal schedules, independent of Qt and the team TaskCreate tools.

One owner holds an exclusive transaction on a separate lock database for its
whole lifetime. No heartbeat expiry can steal work from a slow/live owner.
The data database uses short IMMEDIATE transactions and immutable occurrence
snapshots. SQLite/OS releases the owner lock on process death.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid

from likecc.affairs import WorkspaceDocuments
from likecc.tools.fetch_web_page import explicit_urls, web_url

UTC = timezone.utc
ACTIVE = ("queued", "awaiting_model", "running", "waiting")
LABELS = {"queued": "排队", "awaiting_model": "待确认模型调用", "running": "执行中",
    "waiting": "待确认", "pending": "待处理", "completed": "运行结束",
    "done": "已完成提醒", "cancelled": "已取消", "failed": "失败",
    "interrupted": "已中断，待核对", "blocked_review": "等待核对旧次结果"}


def utc_now():
    return datetime.now(UTC)


def stamp(value):
    if value.tzinfo is None:
        raise ValueError("时钟必须带时区")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def zone(name):
    # These two modern scheduling zones work without Windows' optional tzdata.
    if name == "Asia/Shanghai":
        return timezone(timedelta(hours=8), name)
    if name == "UTC":
        return UTC
    raise ValueError("首版时区支持 Asia/Shanghai 和 UTC；请换算为 UTC 明确时间")


def local_instant(local, timezone_name):
    value = datetime.fromisoformat(local)
    if value.tzinfo is not None:
        raise ValueError("请填写不带偏移的本地时间，并单独选择时区")
    tz = zone(timezone_name)
    aware = value.replace(tzinfo=tz)
    if (aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != value or
            aware.utcoffset() != value.replace(tzinfo=tz, fold=1).utcoffset()):
        raise ValueError("该本地时间存在夏令时歧义或不存在，请改用 UTC 明确时间")
    return aware.astimezone(UTC)


@dataclass
class TaskSpec:
    content: str
    kind: str
    local_at: str
    timezone: str = "Asia/Shanghai"
    repeat: str = "once"
    files: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    model_policy: str = "ask"
    provider: str = ""

    def validated(self, workspace):
        if not self.content.strip() or len(self.content) > 12000:
            raise ValueError("任务内容不能为空或超过 12000 字符")
        if self.kind not in {"reminder", "execute"} or self.repeat not in {"once", "weekly"}:
            raise ValueError("仅支持提醒/执行与一次性/每周")
        if self.model_policy not in {"ask", "allow"}:
            raise ValueError("模型范围必须选择每次确认或本任务周期允许")
        instant = local_instant(self.local_at, self.timezone)
        if instant.year < 2000:
            raise ValueError("只支持 2000 年以后的安排")
        documents = WorkspaceDocuments(workspace)
        result = asdict(self)
        for name in ("files", "outputs"):
            result[name] = list(dict.fromkeys(documents.path(p, write=name == "outputs").relative_to(
                documents.root).as_posix() for p in result[name]))
        result["urls"] = list(dict.fromkeys(str(web_url(u)) for u in self.urls))
        if len(result["urls"]) > 8 or len(result["files"]) > 32 or len(result["outputs"]) > 8:
            raise ValueError("超出本次资料范围数量限制")
        if self.kind == "execute" and not result["outputs"]:
            raise ValueError("执行任务需要明确 Markdown 输出路径")
        return TaskSpec(**result)


def parse_schedule(text, *, now=None, timezone_name="Asia/Shanghai"):
    """Conservative, offline parser; ambiguity never calls a model to guess."""
    now = (now or utc_now()).astimezone(zone(timezone_name))
    repeat = "weekly" if "每周" in text else "once"
    pattern = r"(?:(上午|早上|下午|晚上|晚|中午))?\s*([零〇一二两三四五六七八九十\d]+)(点|[:：])([零〇一二两三四五六七八九十\d]+)?(?:分)?(半)?"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("请补充明确时间，例如明天晚上七点，或每周五下午六点；也可用任务表单填写日期时间")
    match = matches[0]
    if re.search(r"左右|前后|大概|大约|差|之前|之后|刻", text[max(0, match.start()-2):match.end()+2]):
        raise ValueError("时间包含近似或未支持的表达，请填写明确时分")
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    def number(raw):
        if raw.isdecimal():
            return int(raw)
        raw = raw.replace("两", "二").replace("〇", "零")
        try:
            if "十" in raw:
                a, b = raw.split("十")
                return (digits[a] if a else 1) * 10 + (digits[b] if b else 0)
            return digits[raw]
        except (KeyError, ValueError) as exc:
            raise ValueError("无法确定时间，请使用数字时分") from exc
    period, raw, separator, minute, half = match.groups()
    hour = number(raw)
    if not period and hour < 13 and separator == "点":
        raise ValueError("请说明上午或下午；不猜测七点是 07:00 还是 19:00")
    if period and not 1 <= hour <= 12:
        raise ValueError("上午/下午请使用 1 至 12 点")
    if period in {"下午", "晚上", "晚", "中午"}:
        hour = hour % 12 + 12
    elif period:
        hour %= 12
    if half and minute:
        raise ValueError("请使用明确的分钟数，不混合分钟与半点")
    at = now.replace(hour=hour, minute=30 if half else number(minute) if minute else 0, second=0, microsecond=0)
    if repeat == "weekly":
        weekday = re.search(r"每周([一二三四五六日天])", text)
        if not weekday:
            raise ValueError("请补充每周几")
        index = "一二三四五六日".index(weekday[1].replace("天", "日"))
        at += timedelta(days=(index - now.weekday()) % 7)
        if at <= now:
            at += timedelta(days=7)
    elif "明天" in text or "明晚" in text:
        at += timedelta(days=1)
    else:
        date = re.search(r"\d{4}-\d{2}-\d{2}", text)
        if not date:
            raise ValueError("请补充日期，例如明天或 2026-11-21")
        day = datetime.fromisoformat(date[0])
        at = at.replace(year=day.year, month=day.month, day=day.day)
    if at <= now:
        raise ValueError("时间已过去，请指定未来时间")
    kind = "reminder" if "提醒" in text else "execute"
    paths = re.findall(r"`([^`]+\.(?:md|markdown|txt))`", text)
    if not paths:
        paths = re.findall(r"(?<![\w/])([\w./-]+\.(?:md|markdown|txt))", text)
    outputs = [p for p in paths if p.startswith("outputs/")]
    if kind == "execute" and not outputs and len(paths) >= 2:
        outputs = paths[-1:]
    return TaskSpec(text, kind, at.replace(tzinfo=None).isoformat(timespec="seconds"),
        timezone_name, repeat, [p for p in paths if p not in outputs], sorted(explicit_urls(text)), outputs)


class SchedulerOwned(RuntimeError):
    pass


class ScheduleStore:
    def __init__(self, workspace, *, clock=utc_now):
        self.workspace = str(Path(workspace).resolve())
        self.clock = clock
        folder = Path(self.workspace) / ".likecc"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "schedules.sqlite3"
        self._owner = sqlite3.connect(folder / "scheduler-lock.sqlite3", timeout=0)
        try:
            self._owner.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            self._owner.close()
            raise SchedulerOwned("该工作区已有活动调度器；请先退出另一实例") from exc
        try:
            self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (workspace TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, spec TEXT NOT NULL, revision INTEGER NOT NULL,
                    enabled INTEGER NOT NULL, next_due TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                    due_at TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '', started_at TEXT, ended_at TEXT,
                    session_id TEXT, run_id TEXT, evidence TEXT NOT NULL DEFAULT '{}',
                    reviewed_at TEXT,
                    retry_of TEXT UNIQUE REFERENCES executions(id),
                    UNIQUE(task_id, due_at));
            ''')
            row = self.db.execute("SELECT workspace FROM metadata").fetchone()
            if row and row[0] != self.workspace:
                raise ValueError("任务库属于另一工作区；不能复制数据库来迁移授权")
            if not row:
                self.db.execute("INSERT INTO metadata VALUES (?)", (self.workspace,))
            self.recover()
        except BaseException:
            self.close()
            raise

    def close(self):
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None
        if self._owner is not None:
            self._owner.close()
            self._owner = None

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def recover(self):
        # Even a claimed-but-not-started occurrence requires an explicit choice.
        with self.transaction():
            self.db.execute("""UPDATE executions SET status='interrupted', ended_at=?,
                reason=reason || '；上次进程退出/中断。请查看会话、成果和磁盘后明确重试，系统不自动重放。'
                WHERE status IN ('queued','awaiting_model','running','waiting')""", (stamp(self.clock()),))
            # Older versions called every write error write_failed, even after
            # truncating the file. Preserve their evidence and require review.
            rows = self.db.execute("""SELECT id, evidence FROM executions
                WHERE status IN ('completed','failed','cancelled') AND reviewed_at IS NULL""").fetchall()
            for row in rows:
                intents = json.loads(row["evidence"]).get("write_intents", {})
                if any(i.get("status") in {"write_failed", "write_unverified"} for i in intents.values()):
                    self.db.execute("""UPDATE executions SET status='interrupted',
                        reason=reason || '；旧记录存在未核实的写入线索，请核对会话、成果和磁盘后明确重试。'
                        WHERE id=?""", (row["id"],))

    def save(self, spec, *, task_id=None, revision=None):
        spec = spec.validated(self.workspace)
        due = stamp(local_instant(spec.local_at, spec.timezone))
        if due <= stamp(self.clock()):
            raise ValueError("请安排未来的到期时间")
        task_id = task_id or uuid.uuid4().hex
        with self.transaction():
            old = self.db.execute("SELECT revision FROM tasks WHERE id=?", (task_id,)).fetchone()
            if old:
                if revision != old[0]:
                    raise ValueError("任务已变化，请重新查看并确认")
                self.db.execute("UPDATE tasks SET spec=?, revision=revision+1, enabled=1, next_due=? WHERE id=?",
                    (json.dumps(asdict(spec), ensure_ascii=False), due, task_id))
                self.db.execute("""UPDATE executions SET status='cancelled', ended_at=?, reason='安排已修改，尚未开始的旧安排已取消'
                    WHERE task_id=? AND status IN ('queued','awaiting_model')""", (stamp(self.clock()), task_id))
            else:
                if revision is not None:
                    raise ValueError("任务不存在")
                self.db.execute("INSERT INTO tasks VALUES (?,?,1,1,?,?)",
                    (task_id, json.dumps(asdict(spec), ensure_ascii=False), due, stamp(self.clock())))
        return task_id

    def tasks(self):
        return [dict(row) | {"spec": json.loads(row["spec"]), "workspace": self.workspace}
                for row in self.db.execute("SELECT * FROM tasks ORDER BY created_at DESC")]

    def task(self, task_id):
        return next(t for t in self.tasks() if t["id"] == task_id)

    def executions(self, task_id=None):
        rows = self.db.execute("SELECT * FROM executions" + (" WHERE task_id=?" if task_id else "") +
            " ORDER BY due_at DESC, id", (task_id,) if task_id else ())
        return [dict(r) | {"snapshot": json.loads(r["snapshot"]), "evidence": json.loads(r["evidence"]),
            "label": "已中断，已核对" if r["status"] == "interrupted" and r["reviewed_at"] else LABELS[r["status"]]} for r in rows]

    def execution(self, execution_id):
        return next(e for e in self.executions() if e["id"] == execution_id)

    def cancel(self, task_id):
        with self.transaction():
            self.db.execute("UPDATE tasks SET enabled=0, next_due=NULL, revision=revision+1 WHERE id=?", (task_id,))
            self.db.execute("""UPDATE executions SET status='cancelled', ended_at=?, reason='用户取消安排'
                WHERE task_id=? AND status IN ('queued','awaiting_model','pending','blocked_review')""", (stamp(self.clock()), task_id))

    def scan(self):
        now = self.clock()
        with self.transaction():
            for row in self.db.execute("SELECT * FROM tasks WHERE enabled=1 AND next_due<=?", (stamp(now),)).fetchall():
                spec = json.loads(row["spec"])
                due = datetime.fromisoformat(row["next_due"])
                skipped = 0
                next_due = None
                if spec["repeat"] == "weekly":
                    # Local calendar recurrence, never elapsed 7*24h across DST.
                    local = due.astimezone(zone(spec["timezone"])).replace(tzinfo=None)
                    weeks = max(0, (now.astimezone(zone(spec["timezone"])).replace(tzinfo=None) - local).days // 7)
                    local += timedelta(weeks=weeks)
                    due = local_instant(local.isoformat(), spec["timezone"])
                    skipped = weeks
                    next_due = stamp(local_instant((local + timedelta(days=7)).isoformat(), spec["timezone"]))
                reason = (f"合并错过的 {skipped} 个较早周期，仅处理最近一次。" if skipped else "")
                if due < now:
                    reason += "逾期待处理。"
                status = "pending" if spec["kind"] == "reminder" else "queued" if spec["model_policy"] == "allow" else "awaiting_model"
                if spec["kind"] == "execute" and self.db.execute(
                        "SELECT 1 FROM executions WHERE task_id=? AND status='interrupted' AND reviewed_at IS NULL", (row["id"],)).fetchone():
                    status = "blocked_review"
                    reason += "旧次执行结果未知，先查看旧次记录并明确重试；本次不自动调用模型。"
                snapshot = dict(spec, workspace=self.workspace, revision=row["revision"])
                self.db.execute("""INSERT OR IGNORE INTO executions
                    (id,task_id,due_at,snapshot,status,reason) VALUES (?,?,?,?,?,?)""",
                    (uuid.uuid4().hex, row["id"], stamp(due), json.dumps(snapshot, ensure_ascii=False), status, reason))
                self.db.execute("UPDATE tasks SET next_due=? WHERE id=?", (next_due, row["id"]))

    def update(self, execution_id, **values):
        allowed = {"status", "reason", "started_at", "ended_at", "session_id", "run_id", "evidence"}
        if not values.keys() <= allowed:
            raise ValueError("无效执行字段")
        if "evidence" in values:
            values["evidence"] = json.dumps(values["evidence"], ensure_ascii=False)
        self.db.execute("UPDATE executions SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
            (*values.values(), execution_id))

    def start(self, execution_id):
        with self.transaction():
            # A later occurrence may already be queued when the running one
            # becomes interrupted. Recheck at claim time, not only during scan.
            self.db.execute("""UPDATE executions SET status='blocked_review',
                reason='旧次执行结果未知，先查看旧次记录并明确重试；本次不自动调用模型。'
                WHERE id=? AND status='queued' AND EXISTS (
                    SELECT 1 FROM executions AS previous
                    WHERE previous.task_id=executions.task_id
                        AND previous.status='interrupted' AND previous.reviewed_at IS NULL)""", (execution_id,))
            changed = self.db.execute("""UPDATE executions SET status='running', started_at=?
                WHERE id=? AND status='queued'""", (stamp(self.clock()), execution_id)).rowcount
        return changed == 1

    def approve_model(self, execution_id):
        self.db.execute("UPDATE executions SET status='queued', reason='用户允许本次模型调用' WHERE id=? AND status='awaiting_model'",
            (execution_id,))

    def complete_reminder(self, execution_id):
        self.db.execute("UPDATE executions SET status='done', ended_at=? WHERE id=? AND status='pending'",
            (stamp(self.clock()), execution_id))

    def retry(self, execution_id):
        old = self.execution(execution_id)
        if old["status"] not in {"interrupted", "failed", "cancelled", "completed"}:
            raise ValueError("请先查看已结束或中断的执行，再确认新的尝试")
        if not self.task(old["task_id"])["enabled"]:
            raise ValueError("安排已取消，请编辑并重新确认安排")
        if old["snapshot"]["kind"] != "execute":
            raise ValueError("提醒无需执行重试，请修改未来安排")
        # A new, explicitly requested occurrence, never a replay of the old row.
        with self.transaction():
            if self.db.execute("SELECT 1 FROM executions WHERE retry_of=?", (execution_id,)).fetchone():
                return
            due = self.clock()
            while self.db.execute("SELECT 1 FROM executions WHERE task_id=? AND due_at=?", (old["task_id"], stamp(due))).fetchone():
                due += timedelta(microseconds=1)
            self.db.execute("UPDATE executions SET reviewed_at=? WHERE id=?", (stamp(self.clock()), execution_id))
            self.db.execute("""UPDATE executions SET status='cancelled', ended_at=?, reason='用户核对旧次后合并为手动新尝试'
                WHERE task_id=? AND status='blocked_review'""", (stamp(self.clock()), old["task_id"]))
            self.db.execute("""INSERT OR IGNORE INTO executions
                (id,task_id,due_at,snapshot,status,reason,retry_of) VALUES (?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, old["task_id"], stamp(due), json.dumps(old["snapshot"], ensure_ascii=False),
                 "awaiting_model", "用户已核对旧结果并要求新一次尝试；沿用旧次范围，需确认模型调用", execution_id))


def needs_attention(execution):
    """Reviewed interruptions remain audit history, not outstanding decisions."""
    return (execution["status"] in {"pending", "awaiting_model", "waiting", "blocked_review"}
            or execution["status"] == "interrupted" and not execution.get("reviewed_at"))


class ExecutionScope:
    """A hard ceiling, applied before R4 permission rules and human approvals."""
    def __init__(self, snapshot):
        self.spec = snapshot
        self.documents = WorkspaceDocuments(snapshot["workspace"])

    def check(self, tool, arguments):
        if tool.name in {"AskUserQuestion", "ToolSearch"}:
            return
        if tool.name == "FetchWebPage":
            if str(web_url(arguments.get("url"))) in self.spec["urls"]:
                return
        elif tool.name in {"ReadFile", "WriteFile"}:
            path = self.documents.path(arguments.get("file_path"), write=tool.name == "WriteFile")
            local = path.relative_to(self.documents.root).as_posix()
            allowed = self.spec["outputs"] if tool.name == "WriteFile" else self.spec["files"] + self.spec["outputs"]
            if local in allowed:
                return
        raise ValueError("超出本次任务已确认的材料或操作范围；请编辑安排并重新确认")
