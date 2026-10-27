# -*- coding: utf-8 -*-
"""kpls.http — 零依赖 HTTP 小工具（urllib）+ 进程内 TTL 缓存。"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 18.0
DEFAULT_RETRIES = 2

class HttpError(RuntimeError):
    def __init__(self, url: str, status: int, body: str = "", reason: str = ""):
        self.url = url
        self.status = status
        self.body = body
        self.reason = reason
        super().__init__("HTTP %s %s %s" % (status, url, (reason or "")[:200]))


class NetError(RuntimeError):
    pass


def _decode(raw: bytes, encodings: tuple[str, ...]) -> str:
    for enc in encodings + ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    encodings: tuple[str, ...] = (),
    insecure: bool = False,
) -> str:
    """返回文本；4xx/5xx 抛 HttpError，网络层失败抛 NetError。

    insecure=True 跳过证书校验（仅用于本机证书链缺失的上游，如 api.tushare.pro）。
    """
    body = data.encode("utf-8") if isinstance(data, str) else data
    ctx = ssl._create_unverified_context() if insecure else None
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method=method.upper(), headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return _decode(resp.read(), encodings)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            err = HttpError(url, e.code, detail, getattr(e, "reason", "") and str(e.reason) or "")
            if e.code < 500 or attempt >= retries:
                raise err from e
            last = err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = NetError("%s: %s" % (url, e))
            if attempt >= retries:
                raise last from e
        time.sleep(0.4 * (attempt + 1))
    raise last or NetError(url)


def get_text(url: str, **kw) -> str:
    return request(url, method="GET", **kw)


def get_json(url: str, **kw) -> object:
    txt = request(url, method="GET", **kw)
    return load_json(txt, url)


def post_form(url: str, form: dict[str, str] | None = None, **kw) -> str:
    payload = urllib.parse.urlencode(form or {})
    headers = dict(kw.pop("headers", {}) or {})
    headers.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    return request(url, method="POST", data=payload, headers=headers, **kw)


def post_json(url: str, payload: object, **kw) -> object:
    headers = dict(kw.pop("headers", {}) or {})
    headers.setdefault("Content-Type", "application/json; charset=UTF-8")
    txt = request(url, method="POST", data=json.dumps(payload, ensure_ascii=False), headers=headers, **kw)
    return load_json(txt, url)


def load_json(text: str, url: str = "", *, loose: bool = True) -> object:
    """解析 JSON；loose=True 时兼容新浪那种未加引号的 key。"""
    import re

    s = (text or "").strip()
    if not s:
        raise ValueError("空响应: %s" % url)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        if not loose:
            raise
        fixed = re.sub(r"([{,\[]\s*)([A-Za-z_][\w\-]*)\s*:", r'\1"\2":', s)
        fixed = fixed.replace("'", '"')
        return json.loads(fixed)


_CACHE: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: float, fn):
    """简单进程内 TTL 缓存（避免同一轮扫描重复打上游）。"""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def clear_cache() -> None:
    _CACHE.clear()


def qs(url: str, params: dict | None = None) -> str:
    """把 params 合并进 URL 查询串（None/空串跳过）。"""
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None and str(v) != ""}
    if not clean:
        return url
    parts = urllib.parse.urlsplit(url)
    old = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    merged = dict(old)
    merged.update({k: str(v) for k, v in clean.items()})
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(merged)))
