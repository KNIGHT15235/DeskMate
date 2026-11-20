"""Bounded reads of explicit public URLs, with DNS-to-connection pinning."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel, Field

from likecc.tools.base import Tool, ToolResult

MAX_URL = 1024
MAX_BYTES = 512 * 1024
MAX_TEXT = 6500
MAX_REDIRECTS = 3
TOTAL_SECONDS = 20
_REDIRECTS = {301, 302, 303, 307, 308}
_FORMATS = {"text/html", "text/plain", "text/markdown"}


def web_url(value: str) -> httpx.URL:
    if not isinstance(value, str) or len(value) > MAX_URL or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ValueError("URL 无效或过长")
    authority = re.match(r"https?://([^/?#]+)", value, re.IGNORECASE)
    if not authority or "@" in authority[1]:
        raise ValueError("只支持无用户名和密码的 HTTP(S) URL")
    try:
        url = httpx.URL(value).copy_with(fragment=None)
        if not url.host or url.username or url.password or len(str(url)) > MAX_URL:
            raise ValueError
        # URL parsing alone does not prove a host is public. Every actual hop
        # is resolved and validated before the transport is opened.
        host = url.host.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            public_ip(host)
        return url
    except (httpx.InvalidURL, ValueError) as exc:
        raise ValueError("URL 无效或目标不是受支持的公网地址") from exc


def explicit_urls(prompt: str) -> set[str]:
    urls = set()
    for match in re.finditer(r"https?://[^\s<>\"'`，。；、！？）】]+", prompt, re.IGNORECASE):
        try:
            urls.add(str(web_url(match[0].rstrip(".,;)]}"))))
        except ValueError:
            continue
        if len(urls) == 8:
            break
    return urls


def public_ip(value: str) -> str:
    ip = ipaddress.ip_address(value)
    if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_link_local
            or isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo or ip.scope_id)):
        raise ValueError("拒绝非公网网络目标")
    return str(ip)


async def resolve_host(host: str, port: int) -> list[str]:
    rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [row[4][0] for row in rows]


class PageText(HTMLParser):
    _hidden = {"script", "style", "template", "noscript", "svg"}
    _blocks = {"p", "br", "div", "li", "h1", "h2", "h3", "section", "article", "tr", "pre"}

    def __init__(self):
        super().__init__()
        self.hidden = []
        self.in_title = False
        self.title = []
        self.body = []

    def handle_starttag(self, tag, attrs):
        if tag in self._hidden:
            self.hidden.append(tag)
        elif not self.hidden and tag == "title":
            self.in_title = True
        elif not self.hidden and tag in self._blocks:
            self.body.append("\n")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag == "title":
            self.in_title = False
        elif tag in self._blocks:
            self.body.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            (self.title if self.in_title else self.body).append(data)


class FetchParams(BaseModel):
    url: str = Field(max_length=MAX_URL, description="Exact explicit public HTTP(S) URL provided by the user")


class FetchWebPage(Tool):
    name = "FetchWebPage"
    category = "network"
    params_model = FetchParams
    description = "Read a user-supplied public static HTML, plain text or Markdown URL. Returns source ID, status and bounded text."

    def __init__(self, workflow, *, resolver=resolve_host, transport_factory=None):
        self.workflow = workflow
        self.resolver = resolver
        self.transport_factory = transport_factory

    def allowed_url(self, value: str) -> httpx.URL:
        url = web_url(value)
        if str(url) not in self.workflow.urls:
            raise ValueError("请在本次用户消息中明确提供该 URL")
        return url

    async def execute(self, params: FetchParams) -> ToolResult:
        try:
            initial = self.allowed_url(params.url)
            self.workflow.record("web", str(initial), "pending")
        except ValueError as exc:
            return ToolResult(str(exc), True)
        url = initial
        try:
            async with asyncio.timeout(TOTAL_SECONDS):
                for hop in range(MAX_REDIRECTS + 1):
                    if self.workflow.web_denied(str(url)):
                        raise ValueError("网络目标被权限规则拒绝")
                    port = url.port or (443 if url.scheme == "https" else 80)
                    ips = [public_ip(ip) for ip in await self.resolver(url.raw_host.decode("ascii"), port)]
                    if not ips:
                        raise ValueError("没有可用 DNS 地址")
                    # Connect only to a checked IP. Preserve the original Host
                    # and TLS name, and open a fresh client for each hop.
                    pinned = url.copy_with(host=ips[0])
                    host_header = url.netloc.decode("ascii")
                    transport = self.transport_factory() if self.transport_factory else None
                    async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                                 timeout=httpx.Timeout(8.0, connect=5.0)) as client:
                        async with client.stream("GET", pinned, headers={"Host": host_header,
                                "Accept-Encoding": "identity", "User-Agent": "DeskMate/0.2"},
                                extensions={"sni_hostname": url.raw_host.decode("ascii")}) as response:
                            if response.status_code in _REDIRECTS:
                                location = response.headers.get("location")
                                if hop == MAX_REDIRECTS or not location:
                                    raise ValueError("重定向超过上限或缺少 Location")
                                target = web_url(str(url.join(location)))
                                if url.scheme == "https" and target.scheme != "https":
                                    raise ValueError("拒绝 HTTPS 降级重定向")
                                url = target
                                continue
                            if not response.is_success:
                                raise ValueError(f"HTTP {response.status_code}")
                            title, body = await self._text(response)
                            break
        except (TimeoutError, httpx.TimeoutException):
            return self._failure(initial, url, "网页读取超时")
        except (httpx.HTTPError, OSError, httpx.InvalidURL):
            return self._failure(initial, url, "网络、DNS 或 TLS 请求失败")
        except (ValueError, LookupError) as exc:
            return self._failure(initial, url, str(exc))
        truncated = len(body) > MAX_TEXT
        source = self.workflow.record("web", str(initial), "truncated" if truncated else "read",
                                      final_url=str(url), title=title, time=self._time())
        return ToolResult(f"{source['id']} | {source['status']} | {title}\n输入 URL: {initial}\n"
                          f"最终 URL: {url}\n读取时间: {source['time']}\n资料正文：\n{body[:MAX_TEXT]}")

    def _failure(self, initial, url, reason):
        now = self._time()
        source = self.workflow.record("web", str(initial), "failed", final_url=str(url), time=now)
        return ToolResult(f"{source['id']} | failed | {reason}\n输入 URL: {initial}\n实际目标 URL: {url}\n时间: {now}", True)

    @staticmethod
    def _time() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    async def _text(response: httpx.Response) -> tuple[str, str]:
        media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media not in _FORMATS:
            raise ValueError("不支持的网页类型，只接受静态 HTML、纯文本或 Markdown")
        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
            raise ValueError("不读取压缩响应")
        declared = response.headers.get("content-length", "")
        if declared.isdecimal() and int(declared) > MAX_BYTES:
            raise ValueError("网页响应超过 512 KiB")
        body = bytearray()
        async for chunk in response.aiter_raw():
            if len(body) + len(chunk) > MAX_BYTES:
                raise ValueError("网页响应超过 512 KiB")
            body.extend(chunk)
        text = body.decode(response.encoding or "utf-8", errors="replace")
        if media == "text/html":
            parser = PageText()
            parser.feed(text)
            parser.close()
            title = " ".join("".join(parser.title).split())[:160]
            text = "".join(parser.body)
        else:
            title = ""
        return title, "\n".join(line.strip() for line in text.splitlines() if line.strip())
