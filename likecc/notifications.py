"""Workspace notification projection. No Qt, model calls or tool execution.

ScheduleStore owns the connection and transaction. Execution rows and durable
interaction facts are the source of truth; this projection owns reading/snoozing
and delivery only. Reconciliation is also safe to repeat after an older writer.
"""
from datetime import datetime, timedelta
import json
import re
import uuid


DEFAULT_SETTINGS = {"enabled": False, "start": "22:00", "end": "08:00", "timezone": "Asia/Shanghai"}


def is_quiet(now, settings):
    from .scheduling import zone
    if not settings["enabled"]:
        return False
    at = now.astimezone(zone(settings["timezone"])).strftime("%H:%M")
    start, end = settings["start"], settings["end"]
    # Equal endpoints deliberately mean all day, not a zero length interval.
    return start <= at < end if start < end else at >= start or at < end


def outcome_text(execution, requests):
    evidence = execution["evidence"]
    artifacts = evidence.get("artifacts", [])
    intents = evidence.get("write_intents", {}).values()
    lines = []
    if any(i.get("status") in {"write_unverified", "write_failed"} for i in intents):
        lines.append("写入结果未知，可能已有部分或全部文件；请核对会话、成果和磁盘。")
    if any(r["tool_name"] == "WriteFile" and r["resolution"] == "deny" for r in requests):
        lines.append("本次有写入被拒绝。")
    if not artifacts:
        lines.append("没有已写入的成果记录。")
    labels = {"verified": "文件已回读核对", "written": "已写入，未回读核对",
              "readback_failed": "回读未通过", "write_unverified": "写入结果未知，待核对"}
    for item in artifacts:
        lines.append(f"{item['path']}：{labels.get(item['status'], '成果状态待核对')}。")
    return "\n".join(lines)


class NotificationLedger:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS notification_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notification_requests (
                request_id TEXT NOT NULL, run_id TEXT NOT NULL, session_id TEXT NOT NULL,
                execution_id TEXT REFERENCES executions(id), tool_id TEXT NOT NULL,
                kind TEXT NOT NULL, tool_name TEXT NOT NULL, description TEXT NOT NULL,
                active INTEGER NOT NULL, resolution TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(run_id, request_id));
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
                task_id TEXT REFERENCES tasks(id), execution_id TEXT REFERENCES executions(id),
                run_id TEXT, session_id TEXT, request_id TEXT, kind TEXT NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL, priority INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'unread', valid INTEGER NOT NULL DEFAULT 1,
                snoozed_until TEXT, generation INTEGER NOT NULL DEFAULT 0,
                alerted_generation INTEGER NOT NULL DEFAULT -1,
                revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        ''')
        self.bootstrap = not self.db.execute("SELECT 1 FROM notification_meta WHERE key='initialized'").fetchone()

    def _stamp(self, value=None):
        from .scheduling import stamp
        return stamp(value or self.store.clock())

    def _meta(self, key, default):
        row = self.db.execute("SELECT value FROM notification_meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO notification_meta VALUES (?,?)", (key, json.dumps(value)))

    def settings(self):
        return self._meta("quiet", DEFAULT_SETTINGS.copy())

    def configure(self, settings):
        from .scheduling import zone
        if set(settings) != set(DEFAULT_SETTINGS) or type(settings["enabled"]) is not bool:
            raise ValueError("免打扰设置无效")
        for key in ("start", "end"):
            if not isinstance(settings[key], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", settings[key]):
                raise ValueError("免打扰时间请使用 HH:MM")
        zone(settings["timezone"])
        with self.store.transaction():
            self._put_meta("quiet", settings)

    def recover(self):
        # A persisted permission request is history, never a resumable grant.
        self.db.execute("UPDATE notification_requests SET active=0, resolution='interrupted' WHERE active=1")

    def request(self, event, execution_id):
        data = event["data"]
        with self.store.transaction():
            self.db.execute('''INSERT OR IGNORE INTO notification_requests
                (request_id,run_id,session_id,execution_id,tool_id,kind,tool_name,description,active)
                VALUES (?,?,?,?,?,?,?,?,1)''', (data["request_id"], event["run_id"], event["session_id"],
                execution_id, data["tool_id"], event["type"], data.get("tool_name", "AskUserQuestion"),
                data.get("description", "请打开原问题卡片补充回答")[:2000]))
            active = bool(self.db.execute("SELECT active FROM notification_requests WHERE run_id=? AND request_id=?",
                (event["run_id"], data["request_id"])).fetchone()[0])
            if active and execution_id:
                self.db.execute("UPDATE executions SET status='waiting', reason='需要本次权限决定或补充信息' WHERE id=?",
                                (execution_id,))
        return active

    def resolve(self, run_id, *, request_id=None, tool_id=None, resolution="ended"):
        with self.store.transaction():
            where, params = "run_id=? AND active=1", [run_id]
            if request_id is not None:
                where += " AND request_id=?"
                params.append(request_id)
            if tool_id is not None:
                where += " AND tool_id=?"
                params.append(tool_id)
            self.db.execute("UPDATE notification_requests SET active=0,resolution=? WHERE " + where,
                            [resolution, *params])

    def active_requests(self):
        """Persisted unresolved requests; the controller must check live Futures."""
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM notification_requests WHERE active=1")]

    def reconcile(self):
        """Called before every source transaction commits; insert keys never change."""
        executions = {e["id"]: e for e in self.store.executions()}
        requests = [dict(r) for r in self.db.execute("SELECT * FROM notification_requests")]
        desired = {}

        def add(key, kind, title, body, priority, execution=None, request=None):
            e, r = execution or {}, request or {}
            desired[key] = (e.get("task_id"), e.get("id"), r.get("run_id", e.get("run_id")),
                r.get("session_id", e.get("session_id")), r.get("request_id"), kind, title, body, priority)

        for e in executions.values():
            status = e["status"]
            title = {"pending": "提醒到期", "awaiting_model": "等待本次模型调用确认",
                "blocked_review": "等待核对旧次结果", "interrupted": "中断待核对",
                "failed": "运行失败", "completed": "运行结束", "cancelled": "本次执行已取消"}.get(status)
            if not title or e.get("reviewed_at"):
                continue
            kind = {"pending": "reminder", "awaiting_model": "model"}.get(status, status)
            details = outcome_text(e, [r for r in requests if r["execution_id"] == e["id"]]) if status in {
                "interrupted", "failed", "completed", "cancelled"} else e["reason"]
            if status in {"interrupted", "failed", "completed", "cancelled"} and e["reason"]:
                details = e["reason"] + "\n" + details
            add(f"execution:{e['id']}:{kind}", kind, title,
                e["snapshot"]["content"][:500] + "\n" + details, 0 if status in {
                    "awaiting_model", "blocked_review", "interrupted", "failed"} else 1, e)
        for r in requests:
            e = executions.get(r["execution_id"])
            if r["active"] and (e is None or e["status"] in {"waiting", "running"}):
                add(f"request:{r['run_id']}:{r['request_id']}", "request",
                    "等待本次工具权限" if r["kind"] == "PermissionRequest" else "等待补充回答",
                    r["tool_name"] + "：" + r["description"], 0, e, r)
        existing = {r["event_key"]: dict(r) for r in self.db.execute("SELECT * FROM notifications")}
        for key, values in desired.items():
            old = existing.get(key)
            if old is None:
                silent = self.bootstrap and values[5] in {"completed", "cancelled"}
                self.db.execute('''INSERT INTO notifications
                    (id,event_key,task_id,execution_id,run_id,session_id,request_id,kind,title,body,priority,
                     state,alerted_generation,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (uuid.uuid4().hex, key, *values, "handled" if silent else "unread", 0 if silent else -1, self._stamp()))
            elif tuple(old[k] for k in ("task_id", "execution_id", "run_id", "session_id", "request_id",
                    "kind", "title", "body", "priority")) != values or not old["valid"]:
                self.db.execute('''UPDATE notifications SET task_id=?,execution_id=?,run_id=?,session_id=?,
                    request_id=?,kind=?,title=?,body=?,priority=?,valid=1,revision=revision+1 WHERE id=?''', (*values, old["id"]))
        for key, old in existing.items():
            if key not in desired and old["valid"]:
                self.db.execute("UPDATE notifications SET valid=0,revision=revision+1 WHERE id=?", (old["id"],))
        if self.bootstrap:
            self._put_meta("initialized", True)
        self.bootstrap = False

    def rows(self):
        return [dict(r) | {"workspace": self.store.workspace} for r in self.db.execute('''
            SELECT * FROM notifications ORDER BY valid DESC, (state='handled'), priority, created_at DESC, id''')]

    def get(self, notification_id):
        row = self.db.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if row is None:
            raise ValueError("通知不存在于当前工作区")
        return dict(row)

    def change(self, notification_id, revision, action, *, minutes=10):
        with self.store.transaction():
            row = self.get(notification_id)
            if row["revision"] != revision:
                raise ValueError("通知已变化，请刷新后查看")
            if action == "view":
                # Viewing does not discard an explicitly requested future reminder.
                if row["state"] == "unread":
                    self.db.execute("UPDATE notifications SET state='viewed',revision=revision+1 WHERE id=?", (notification_id,))
            elif action == "dismiss":
                self.db.execute("UPDATE notifications SET state='handled',snoozed_until=NULL,revision=revision+1 WHERE id=?", (notification_id,))
            elif action == "snooze":
                if not row["valid"] or row["state"] == "handled":
                    raise ValueError("该事项已结束或提醒已关闭，只能查看历史")
                if type(minutes) is not int or not 1 <= minutes <= 10080:
                    raise ValueError("稍后提醒范围为 1 分钟至 7 天")
                self.db.execute('''UPDATE notifications SET state='snoozed',snoozed_until=?,
                    generation=generation+1,revision=revision+1 WHERE id=?''',
                    (self._stamp(self.store.clock() + timedelta(minutes=minutes)), notification_id))
            else:
                raise ValueError("未知通知操作")

    def due(self):
        if is_quiet(self.store.clock(), self.settings()):
            return []
        return [r for r in self.rows() if r["valid"] and r["state"] != "handled"
            and r["alerted_generation"] < r["generation"]
            and (not r["snoozed_until"] or r["snoozed_until"] <= self._stamp())]

    def claim_alert(self):
        """Persist one aggregate delivery claim. Crashing after claim may lose a
        balloon; the center is durable. Never promise OS exactly-once delivery.
        """
        with self.store.transaction():
            self.reconcile()
            rows = self.due()
            last = self._meta("last_alert", None)
            if not rows or last and self.store.clock() < datetime.fromisoformat(last) + timedelta(seconds=30):
                return None
            for r in rows:
                self.db.execute('''UPDATE notifications SET alerted_generation=generation,
                    state=CASE WHEN state='snoozed' THEN 'unread' ELSE state END,
                    snoozed_until=NULL,revision=revision+1 WHERE id=?''', (r["id"],))
            self._put_meta("last_alert", self._stamp())
            return {"token": uuid.uuid4().hex, "workspace": self.store.workspace,
                "items": [{"id": r["id"], "generation": r["generation"]} for r in rows],
                "title": rows[0]["title"] if len(rows) == 1 else f"DeskMate · {len(rows)} 条新事项",
                "body": rows[0]["body"][:180] if len(rows) == 1 else "有到期、待决定或执行结果。请打开通知中心选择具体事项。"}
