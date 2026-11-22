"""Explicit desktop profile for bounded materials and verified Markdown artifacts."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PureWindowsPath

from likecc.agent import ToolResultEvent, ToolUseEvent
from likecc.permissions.sandbox import PathSandbox
from likecc.tools.base import ToolResult
from likecc.tools.fetch_web_page import FetchWebPage, explicit_urls, web_url
from likecc.tools.file_state_cache import FileStateCache
from likecc.tools.read_file import ReadFile
from likecc.tools.write_file import WriteFile

MAX_FILE_BYTES = 128 * 1024
MAX_FILE_TEXT = 6500
MAX_SOURCES = 32
MAX_ARTIFACTS = 8
MARKDOWN = {".md", ".markdown"}


class WorkspaceDocuments:
    def __init__(self, work_dir):
        self.root = Path(work_dir).resolve()

    def path(self, value: str, *, write=False) -> Path:
        if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
            raise ValueError("需要有效的工作区文件路径")
        windows = PureWindowsPath(value)
        if (value.startswith(("//", "\\")) or windows.drive and (os.name != "nt" or not windows.is_absolute())
                or windows.is_reserved() or any(":" in part for part in windows.parts[1 if windows.anchor else 0:])):
            raise ValueError("不支持网络路径、设备路径或替代数据流")
        path = (self.root / value).resolve()
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("资料路径超出所选工作区") from exc
        if not relative.parts or any(part.startswith(".") for part in relative.parts):
            raise ValueError("资料模式不读取或写入隐藏文件及应用配置目录")
        formats = MARKDOWN if write else MARKDOWN | {".txt"}
        if path.suffix.lower() not in formats:
            raise ValueError("输出仅支持 Markdown" if write else "材料仅支持 UTF-8 文本和 Markdown")
        if path.exists() and not path.is_file():
            raise ValueError("资料必须是普通文件")
        return path

    def read_text(self, path: Path) -> str:
        path = self.path(str(path))
        if not path.is_file():
            raise ValueError("资料必须是普通文件")
        with path.open("rb") as file:
            data = file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("材料超过 128 KiB")
        return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


class MaterialsWorkflow:
    def __init__(self, work_dir, rules):
        self.documents = WorkspaceDocuments(work_dir)
        self.rules = rules
        self.cache = FileStateCache(read_text=self.documents.read_text)
        self.on_change = None
        self.begin("")

    def begin(self, prompt):
        self.urls = explicit_urls(prompt)
        self.sources = {}
        self.artifacts = {}
        self.write_intents = {}
        self._calls = {}
        self.cache.clear()

    def web_denied(self, url):
        return self.rules.evaluate("FetchWebPage", url, deny_first=True) == "deny"

    def record(self, kind, target, status, **metadata):
        key = kind, target
        if key not in self.sources and len(self.sources) >= MAX_SOURCES:
            raise ValueError("本次任务最多记录 32 份来源")
        previous = self.sources.get(key)
        identifier = previous["id"] if previous else f"S{len(self.sources) + 1}"
        # A retry rejected before opening the resource must not erase a real read.
        if previous and status in {"pending", "failed"} and previous["status"] in {"read", "truncated"}:
            return previous
        source = {"id": identifier, "kind": kind, "target": target, "status": status, **metadata}
        self.sources[key] = source
        self.checkpoint()
        return source

    def checkpoint(self):
        if self.on_change is not None:
            self.on_change()

    def observe(self, event):
        if isinstance(event, ToolUseEvent) and event.tool_name in {"FetchWebPage", "ReadFile"}:
            try:
                if event.tool_name == "FetchWebPage":
                    url = str(web_url(event.arguments.get("url")))
                    if url in self.urls:
                        self._calls[event.tool_id] = ("web", url)
                else:
                    path = self.documents.path(event.arguments.get("file_path"))
                    local = path.relative_to(self.documents.root).as_posix()
                    self._calls[event.tool_id] = ("artifact" if local in self.artifacts else "file", local)
            except (ValueError, RuntimeError, OSError):
                pass
        elif isinstance(event, ToolResultEvent):
            target = self._calls.pop(event.tool_id, None)
            if target and event.is_error:
                if target[0] == "artifact":
                    self.artifacts[target[1]]["status"] = "readback_failed"
                    return
                previous = self.sources.get(target)
                if previous is None or previous["status"] == "pending":
                    try:
                        self.record(*target, "failed", time=FetchWebPage._time())
                    except ValueError:
                        pass  # source quota already reported by the tool

    def finish(self):
        for target in self._calls.values():
            if target[0] == "artifact":
                continue
            previous = self.sources.get(target)
            if previous is None or previous["status"] == "pending":
                try:
                    self.record(*target, "interrupted", time=FetchWebPage._time())
                except ValueError:
                    break
        self._calls.clear()
        self.checkpoint()

    def summary(self):
        return {
            "sources": [dict(source) for source in self.sources.values()],
            "artifacts": [{"path": path, "status": entry["status"]} for path, entry in self.artifacts.items()],
        }

    def ledger(self):
        def code(text):
            # Entities are literal inside CommonMark code spans. Preserve
            # ampersands and repeated spaces; choose a safe backtick delimiter.
            fence = "`" * (1 + max((len(s) for s in re.findall(r"`+", text)), default=0))
            pad = " " if text.startswith(("`", " ")) or text.endswith(("`", " ")) else ""
            return fence + pad + text + pad + fence

        rows = []
        for source in self.sources.values():
            if source["status"] == "pending":
                continue
            target = source["target"]
            final = source.get("final_url", "")
            title = source.get("title", "")
            detail = f" · 最终 URL {code(final)}" if final and final != target else ""
            if title:
                detail += f" · {code(title)}"
            if source.get("time"):
                detail += f" · {source['time']}"
            rows.append(f"- {source['id']} · {source['status']} · {code(target)}{detail}")
        return "\n".join(rows) or "- 本次没有已记录的读取结果。"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MaterialRead(ReadFile):
    is_concurrency_safe = False  # keep source IDs in tool execution order

    def __init__(self, workflow):
        self.workflow = workflow
        super().__init__(file_state_cache=workflow.cache, read_text=workflow.documents.read_text)

    async def execute(self, params):
        workflow = self.workflow
        try:
            path = workflow.documents.path(params.file_path)
            local = path.relative_to(workflow.documents.root).as_posix()
            if params.offset < 0 or params.limit < 1:
                raise ValueError("资料读取需要非负偏移与正数行数")
            artifact = workflow.artifacts.get(local)
            if artifact is None:
                workflow.record("file", local, "pending")
        except (ValueError, RuntimeError, OSError) as exc:
            return ToolResult(str(exc), True)
        result = await super().execute(params.model_copy(update={"file_path": str(path)}))
        if result.is_error:
            if artifact is not None:
                artifact["status"] = "readback_failed"
                workflow.checkpoint()
            else:
                workflow.record("file", local, "failed", time=FetchWebPage._time())
            return result
        actual = workflow.cache.content(str(path))
        truncated = params.offset > 0 or params.limit < len(actual.splitlines()) or len(result.output) > MAX_FILE_TEXT
        body = result.output[:MAX_FILE_TEXT]
        if truncated:
            body += "\n[返回文本已截断]"
        if artifact is not None:
            if digest(actual) != artifact["digest"]:
                artifact["status"] = "readback_failed"
                workflow.checkpoint()
                return ToolResult(f"回读与本次写入不一致：{local}", True)
            artifact["status"] = "verified"
            workflow.checkpoint()
            return ToolResult(f"成果已回读核对（全文摘要一致）：{local}\n{body}")
        source = workflow.record("file", local, "truncated" if truncated else "read", time=FetchWebPage._time())
        return ToolResult(f"{source['id']} | {source['status']} | {local}\n资料正文：\n{body}")


class MaterialWrite(WriteFile):
    def __init__(self, workflow):
        self.workflow = workflow
        super().__init__(file_state_cache=workflow.cache)

    async def execute(self, params):
        workflow = self.workflow
        try:
            path = workflow.documents.path(params.file_path, write=True)
            local = path.relative_to(workflow.documents.root).as_posix()
            if local not in workflow.artifacts and len(workflow.artifacts) >= MAX_ARTIFACTS:
                raise ValueError("本次任务最多写入 8 个成果文件")
            normalized = params.content.replace("\r\n", "\n").replace("\r", "\n")
            if "\n## 来源（工具记录）" in "\n" + normalized:
                raise ValueError("来源（工具记录）由工具生成，请从拟写入内容中移除该标题")
            citations = set(re.findall(r"\[(S[0-9]+)\]", normalized))
            readable = {s["id"] for s in workflow.sources.values() if s["status"] in {"read", "truncated"}}
            if citations - readable:
                raise ValueError("成果引用了没有成功读取的来源；请在限制说明中描述，勿作为依据")
            text = normalized.rstrip() + "\n\n## 来源（工具记录）\n\n" + workflow.ledger() + "\n"
            if len(text.replace("\n", os.linesep).encode("utf-8")) > MAX_FILE_BYTES:
                raise ValueError("Markdown 成果超过 128 KiB")
        except (ValueError, RuntimeError, OSError) as exc:
            return ToolResult(str(exc), True)
        # Persist a conservative clue BEFORE a write can have side effects.
        workflow.write_intents[local] = {"status": "write_unverified", "digest": digest(text)}
        if local in workflow.artifacts:
            workflow.artifacts[local]["status"] = "write_unverified"
        workflow.checkpoint()
        result = await super().execute(params.model_copy(update={"file_path": str(path), "content": text}))
        if result.is_error:
            workflow.write_intents[local]["status"] = "write_failed"
            workflow.checkpoint()
            return result
        workflow.write_intents[local]["status"] = "written"
        workflow.artifacts[local] = {"status": "written", "digest": digest(text)}
        workflow.checkpoint()
        workflow.cache.forget(str(path))
        return ToolResult(f"已写入 {local}；请用 ReadFile 回读核对成果。")


def install_materials_profile(runtime, **fetch_options):
    workflow = MaterialsWorkflow(runtime.work_dir, runtime.checker.rule_engine)
    runtime.checker.sandbox = PathSandbox(runtime.work_dir, allow_system_temp=False)
    runtime.checker.materials = workflow.documents
    runtime.agent.affairs_mode = True
    for name in ("Bash", "EditFile", "Glob", "Grep"):
        runtime.registry.disable(name)
    runtime.registry.register(MaterialRead(workflow))
    runtime.registry.register(MaterialWrite(workflow))
    runtime.registry.register(FetchWebPage(workflow, **fetch_options))
    runtime.registry.register_file_cache_clearer(workflow.cache.clear)
    return workflow
