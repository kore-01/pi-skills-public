# -*- coding: utf-8 -*-
"""kpls.catalog — 接口目录（assets/apis.json，152 条：开盘啦官方 + py.590 平台 + Tushare + 新浪 + 东财）。"""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from . import config


class CatalogError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def load() -> dict:
    path = config.CATALOG_FILE
    if not path.is_file():
        raise CatalogError("接口目录缺失: %s" % path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):  # 容错：纯数组形态
        data = {"apis": data}
    data.setdefault("apis", [])
    return data


def apis() -> list[dict]:
    return list(load().get("apis") or [])


@functools.lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in apis():
        if a.get("id"):
            out[str(a["id"])] = a
    return out


def find(api_id: str) -> dict:
    entry = _index().get(str(api_id).strip())
    if not entry:
        sugg = [x for x in _index() if api_id.lower() in x.lower()][:8]
        raise CatalogError("接口 id 不存在: %s%s" % (api_id, ("（相近: %s）" % ", ".join(sugg)) if sugg else ""))
    return entry


def meta() -> dict:
    d = load()
    return {k: v for k, v in d.items() if k != "apis"}


def search(keyword: str = "", *, domain: str = "", category: str = "", tag: str = "", limit: int = 0) -> list[dict]:
    kw = (keyword or "").strip().lower()
    out = []
    for a in apis():
        if domain and domain.lower() not in str(a.get("domain", "")).lower():
            continue
        if category and category.lower() not in str(a.get("category", "")).lower():
            continue
        if tag and tag.lower() not in ",".join(str(t) for t in a.get("tags") or []).lower():
            continue
        if kw:
            hay = " ".join(
                [str(a.get("id", "")), str(a.get("name", "")), str(a.get("category", "")),
                 str(a.get("returns", "")), " ".join(str(t) for t in a.get("tags") or [])]
            ).lower()
            if kw not in hay:
                continue
        out.append(a)
    return out[:limit] if limit else out


def categories() -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for a in apis():
        key = str(a.get("category") or "-")
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def source_of(api: dict) -> str:
    """判定数据源：kpl / py590 / tushare / sina / eastmoney / other。"""
    url = str(api.get("url") or "")
    dom = str(api.get("domain") or "")
    if url.startswith("tushare://") or "tushare.pro" in dom:
        return "tushare"
    if url.startswith("strategy://") or "py.590" in dom or "py.590.net" in url:
        return "py590"
    if "longhuvip.com" in dom or "longhuvip.com" in url:
        return "kpl"
    if "sinajs" in url or "sina.com.cn" in url or url.startswith("sina://") or "sinajs" in dom:
        return "sina"
    if "eastmoney.com" in url or "eastmoney.com" in dom:
        return "eastmoney"
    return "other"


def params_spec(api: dict) -> list[dict]:
    return list(api.get("params") or [])


def required_keys(api: dict) -> list[str]:
    return [str(p.get("key")) for p in params_spec(api) if p.get("required")]


def brief(api: dict) -> dict:
    return {
        "id": api.get("id"),
        "name": api.get("name"),
        "category": api.get("category"),
        "source": source_of(api),
        "domain": api.get("domain"),
        "method": api.get("method"),
        "required": required_keys(api),
        "optional": [str(p.get("key")) for p in params_spec(api) if not p.get("required")],
        "returns": str(api.get("returns") or "")[:200],
        "disabled": bool(api.get("disabled")),
    }


PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def placeholders_in(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text or "")


def as_jsonable(obj: Any) -> Any:
    return obj
