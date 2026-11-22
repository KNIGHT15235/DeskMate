import re

import httpx
import pytest
from markdown_it import MarkdownIt

from likecc.affairs import MaterialsWorkflow, MaterialWrite
from likecc.permissions.rules import Rule, RuleEngine
from likecc.tools.fetch_web_page import FetchWebPage, FetchParams
from likecc.tools.work_dir import tool_working_directory
from test_materials_workflow import public_resolver, response


@pytest.mark.parametrize("effect", ["allow", "deny"])
def test_web_rules_normalize_host_but_preserve_path_and_query(effect):
    rule = Rule("FetchWebPage", "https://EXAMPLE.org./Notes?Token=Ab*", effect)
    assert rule.matches("FetchWebPage", "HTTPS://example.ORG/Notes?Token=Abc")
    assert not rule.matches("FetchWebPage", "https://example.org/notes?Token=Abc")
    assert not rule.matches("FetchWebPage", "https://example.org/Notes?token=abc")
    assert not rule.matches("FetchWebPage", "https://example.org/NotesXToken=Abc")
    assert Rule("FetchWebPage", "https://*.EXAMPLE.org/*", effect).matches(
        "FetchWebPage", "https://docs.example.org/Case")


@pytest.mark.asyncio
async def test_markdown_source_identifiers_roundtrip(tmp_path):
    workflow = MaterialsWorkflow(tmp_path, RuleEngine())
    targets = ["https://example.org/Notes?a=1&b=2", "notes  with ` ticks.md"]
    for kind, target in zip(("web", "file"), targets):
        workflow.record(kind, target, "read")
    with tool_working_directory(tmp_path):
        tool = MaterialWrite(workflow)
        result = await tool.execute(tool.params_model(file_path="out.md", content="# Result"))
    assert not result.is_error
    text = (tmp_path / "out.md").read_text(encoding="utf-8")
    # CommonMark code spans use a delimiter longer than any contained backticks.
    copied = []
    for line in text.splitlines():
        if line.startswith("- S"):
            span = line.split(" · ", 2)[2]
            match = re.fullmatch(r"(`+)(.*?)\1", span)
            assert match
            copied.append(match[2].strip(" "))
    assert copied == targets
    tokens = MarkdownIt().parse(text)
    assert [child.content for token in tokens for child in (token.children or []) if child.type == "code_inline"] == targets


@pytest.mark.asyncio
@pytest.mark.parametrize("body,media", [(b"", "text/plain"),
    (b"<title>Title</title><script>hidden</script><p>  </p>", "text/html")])
async def test_empty_web_is_limitation_and_cannot_be_cited(tmp_path, body, media):
    workflow = MaterialsWorkflow(tmp_path, RuleEngine())
    url = "https://example.org/empty"
    workflow.begin(url)
    fetch = FetchWebPage(workflow, resolver=public_resolver,
        transport_factory=lambda: httpx.MockTransport(lambda _: response(data=body, media=media)))
    result = await fetch.execute(FetchParams(url=url))
    assert "无可用正文" in result.output
    assert workflow.summary()["sources"][0]["status"] == "empty"
    tool = MaterialWrite(workflow)
    with tool_working_directory(tmp_path):
        denied = await tool.execute(tool.params_model(file_path="out.md", content="claim [S1]"))
        assert denied.is_error and not (tmp_path / "out.md").exists()
        allowed = await tool.execute(tool.params_model(file_path="out.md", content="限制：网页无可用正文。"))
        assert not allowed.is_error
    assert "S1 · empty" in (tmp_path / "out.md").read_text(encoding="utf-8")
