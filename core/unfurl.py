"""纯 URL 消息：抓取网页 → 独立会话整理 → 注入主模型上下文。"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .util import report_exception
from . import llm


_URL_ONLY_RE = re.compile(r"^\s*https?://\S+\s*$", re.IGNORECASE)
_MAX_URL_LEN = 2000
_MAX_DOWNLOAD = 512 * 1024
_MAX_EXTRACT_CHARS = 8000
_MAX_REDIRECTS = 5
_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_TEXT_TYPES = (
    "text/html", "text/plain", "text/xml", "text/markdown",
    "application/json", "application/xml", "application/xhtml+xml",
    "application/javascript", "application/rss+xml", "application/atom+xml",
)
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

_SUMMARIZE_PROMPT = (
    "你是网页内容整理助手。把下面的网页正文整理成不超过 400 字的中文摘要，"
    "保留标题、关键信息和群聊里可能用到的要点。只输出摘要正文，不要前后缀。"
)


def is_url_only(text: str) -> bool:
    return bool(_URL_ONLY_RE.match(text or ""))


def _extract_url(text: str) -> str:
    return (text or "").strip()


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global)


def _is_public_http_url(url: str) -> bool:
    if not url or len(url) > _MAX_URL_LEN:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    lowered = host.lower()
    if lowered in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or lowered.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return _is_public_ip(ip)
    except ValueError:
        pass
    return _resolve_public(host)


def _resolve_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not _is_public_ip(ip):
            return False
    return True


def public_target(url: str):
    """Resolve and pin a public destination, retaining the original Host and TLS name."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None:
        raise ValueError('public HTTP(S) URL required')
    if len(url) > _MAX_URL_LEN:
        raise ValueError('URL exceeds length limit')
    normalized = httpx.URL(url)
    host = normalized.raw_host.decode('ascii')
    port = normalized.port or (443 if parsed.scheme == 'https' else 80)
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses or any(not _is_public_ip(ipaddress.ip_address(ip)) for ip in addresses):
        raise ValueError('private or unresolved destination')
    # Connect to the validated address, never perform a second domain lookup.
    addresses.sort(key=lambda ip: ':' in ip)
    return normalized.copy_with(host=addresses[0]), {'Host': normalized.netloc.decode('ascii')}, {'sni_hostname':host}


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        t = " ".join(data.split())
        if not t:
            return
        if self._in_title:
            self.title.append(t)
        else:
            self.parts.append(t)


def _html_to_text(html: str) -> tuple[str, str]:
    parser = _HTMLText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
        return "", " ".join(text.split())
    title = " ".join(parser.title).strip()
    body = " ".join(parser.parts)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body


def _content_is_text(content_type: str) -> bool:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if not ctype:
        return True
    return ctype in _TEXT_TYPES or ctype.startswith("text/")


async def _download(url: str) -> tuple[bytes, str] | None:
    """返回 (raw_bytes, content_type)。失败返回 None。不跟到内网。"""
    current = url
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=False,
            trust_env=False, limits=httpx.Limits(max_keepalive_connections=0),
            headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8"},
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                pinned, headers, extensions = await asyncio.to_thread(public_target, current)
                async with client.stream("GET", pinned, headers=headers, extensions=extensions) as resp:
                    if resp.status_code in _REDIRECT_STATUSES:
                        location = resp.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 400:
                        return None
                    ctype = resp.headers.get("content-type", "")
                    if not _content_is_text(ctype):
                        return None
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= _MAX_DOWNLOAD:
                            break
                    return b"".join(chunks)[:_MAX_DOWNLOAD], ctype
            return None
    except Exception as e:
        # 超时/DNS/连接失败：视为获取不到，不进 Sentry
        if not isinstance(e, (httpx.HTTPError, OSError, TimeoutError)):
            report_exception(e)
        return None



def _decode_body(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    m = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if m:
        charset = m.group(1).strip("\"'")
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


async def _summarize_page(url: str, title: str, body: str) -> str | None:
    snippet = body[:_MAX_EXTRACT_CHARS]
    payload = f"URL: {url}\n"
    if title:
        payload += f"标题: {title}\n"
    payload += f"正文:\n{snippet}"
    try:
        text = await llm.summarize_async(_SUMMARIZE_PROMPT, payload)
        return (text or "").strip() or None
    except Exception as e:
        report_exception(e)
        return None


async def unfurl_url_async(text: str) -> str | None:
    """成功返回「原 URL + [链接: 摘要]」，失败（403/404/超时/非文本等）返回 None。"""
    url = _extract_url(text)
    if not is_url_only(url):
        return None
    downloaded = await _download(url)
    if not downloaded:
        return None
    raw, ctype = downloaded
    if not raw.strip():
        return None
    decoded = _decode_body(raw, ctype)
    ctype_main = (ctype or "").split(";")[0].strip().lower()
    if "html" in ctype_main or decoded.lstrip()[:16].lower().startswith(("<!doctype", "<html")):
        title, body = _html_to_text(decoded)
    else:
        title, body = "", decoded.strip()
    body = body.strip()
    if not body and not title:
        return None

    if len(body) <= 180:
        summary = (f"{title}。{body}" if title else body).strip("。")
    else:
        summary = await _summarize_page(url, title, body)
        if not summary:
            # 整理失败时仍给一段截断正文，避免白抓
            head = body[:400].strip()
            summary = f"{title} {head}".strip() if title else head

    summary = re.sub(r"\s+", " ", summary).strip()
    if not summary:
        return None
    return f"{url}\n[链接: {summary}]"
