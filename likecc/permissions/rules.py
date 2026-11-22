from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal

import yaml

Effect = Literal["allow", "deny"]

_RULE_RE = re.compile(r"^(\w+)\((.+)\)$")

_CONTENT_FIELDS: dict[str, str] = {
    "Bash": "command",
    "ReadFile": "file_path",
    "WriteFile": "file_path",
    "EditFile": "file_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "FetchWebPage": "url",
}

_PATH_FIELDS: dict[str, str] = {
    "ReadFile": "file_path",
    "WriteFile": "file_path",
    "EditFile": "file_path",
    "Glob": "path",
    "Grep": "path",
}


def normalize_web_rule(value: str) -> str:
    """URL glob: scheme/DNS host case-insensitive, rest case-sensitive.

    Only * is a URL wildcard; ? (query separator) and brackets are literal.
    Only the authority is normalized; paths, escapes and queries stay intact.
    File rules deliberately retain their historical platform semantics.
    """
    match = re.match(r"^([^:/]+)://([^/?#]+)(.*)$", value, re.DOTALL)
    if match is None:
        return value
    scheme, authority, tail = match.groups()
    host, colon, port = authority.rpartition(":")
    if not colon or not port.isdecimal():
        host, colon, port = authority, "", ""
    host = host.rstrip(".").lower()
    host = ".".join(label.encode("idna").decode("ascii") for label in host.split("."))
    return f"{scheme.lower()}://{host}{colon}{port}{tail}"


@dataclass(frozen=True)
class Rule:
    tool_name: str
    pattern: str
    effect: Effect


    def matches(self, tool_name: str, content: str) -> bool:
        if self.tool_name != tool_name:
            return False
        if tool_name == "FetchWebPage":
            pattern = re.escape(normalize_web_rule(self.pattern)).replace(r"\*", ".*")
            return re.fullmatch(pattern, normalize_web_rule(content), re.DOTALL) is not None
        return fnmatch(content, self.pattern)


def parse_rule(raw: str, effect: Effect) -> Rule:
    m = _RULE_RE.match(raw.strip())
    if not m:
        raise ValueError(f"无效的规则语法: {raw}")
    return Rule(tool_name=m.group(1), pattern=m.group(2), effect=effect)


def extract_content(tool_name: str, arguments: dict[str, Any]) -> str:
    field = _CONTENT_FIELDS.get(tool_name)
    if field is None:
        return ""
    return str(arguments.get(field, ""))


def extract_path(tool_name: str, arguments: dict[str, Any]) -> str:
    """Return the filesystem path checked by the sandbox for a tool call."""
    field = _PATH_FIELDS.get(tool_name)
    if field is None:
        return ""
    default = "." if tool_name in ("Glob", "Grep") else ""
    return str(arguments.get(field, default))


def _load_rules_file(path: Path) -> list[Rule]:
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    rules: list[Rule] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rule_str = entry.get("rule", "")
        effect = entry.get("effect", "")
        if effect not in ("allow", "deny"):
            continue
        try:
            rules.append(parse_rule(rule_str, effect))
        except ValueError:
            continue
    return rules


class RuleEngine:


    def __init__(
        self,
        user_rules_path: Path | None = None,
        project_rules_path: Path | None = None,
        local_rules_path: Path | None = None,
        *,
        inherited_denials: tuple[Rule, ...] = (),
    ) -> None:
        self._user_path = user_rules_path
        self._project_path = project_rules_path
        self._local_path = local_rules_path
        self._inherited_denials = tuple(rule for rule in inherited_denials if rule.effect == "deny")

    def clone_for_subagent(self) -> RuleEngine:
        """Retain policy and denial snapshots without inheriting local approvals."""
        local_rules = _load_rules_file(self._local_path) if self._local_path else []
        denials = self._inherited_denials + tuple(rule for rule in local_rules if rule.effect == "deny")
        return RuleEngine(
            user_rules_path=self._user_path,
            project_rules_path=self._project_path,
            inherited_denials=denials,
        )

    def _load_tiers(self) -> list[list[Rule]]:
        tiers: list[list[Rule]] = []
        for p in (self._user_path, self._project_path, self._local_path):
            tiers.append(_load_rules_file(p) if p else [])
        return tiers


    def evaluate(self, tool_name: str, content: str, *, deny_first: bool = False) -> Effect | None:
        if any(rule.matches(tool_name, content) for rule in self._inherited_denials):
            return "deny"
        tiers = self._load_tiers()
        if deny_first and any(r.effect == "deny" and r.matches(tool_name, content) for tier in tiers for r in tier):
            return "deny"
        for rules in tiers:
            for rule in reversed(rules):
                if rule.matches(tool_name, content):
                    return rule.effect
        return None


    def append_local_rule(self, rule: Rule) -> None:
        if self._local_path is None:
            return
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        existing = _load_rules_file(self._local_path)
        existing.append(rule)
        entries = [{"rule": f"{r.tool_name}({r.pattern})", "effect": r.effect} for r in existing]
        self._local_path.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")
