# -*- coding: utf-8 -*-
"""kpls.catalog — 接口目录（assets/apis.json，152 条：开盘啦官方 + py.590 平台 + Tushare + 新浪 + 东财）。

分片支持
--------
原始 `apis.json` 约 128 KB，部分安装环境对**单文件体积**有限制，会导致整个技能
导入中断（只落 SKILL.md）。为绕开这个限制，目录也可拆成若干分片：

    assets/apis.part00.json   ← 每个分片是一个完整的 JSON 数组（条目子集）
    assets/apis.part01.json
    ...

`load()` 会按文件名排序读取全部分片并合并 `apis` 列表。两个入口等价：

    assets/apis.json          ← 完整文件
    assets/apis.part*.json    ← 分片（可与完整文件共存，自动合并去重）
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from . import config


class CatalogError(RuntimeError):
    pass


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CatalogError("接口目录解析失败: %s (%s)" % (path, e)) from None


def _part_files() -> list[Path]:
    """按文件名排序返回所有分片（apis.part00.json, apis.part01.json, ...）。"""
    assets = config.ASSETS_DIR
    try:
        files = sorted(assets.glob("apis.part*.json"))
    except OSError:
        files = []
    return files


@functools.lru_cache(maxsize=1)
def load() -> dict:
    """加载接口目录。合并完整文件与分片；同一 id 保留先出现者。"""
    parts = _part_files()
    main = config.CATALOG_FILE

    if not main.is_file() and not parts:
        raise CatalogError("接口目录缺失: %s（也没有分片 assets/apis.part*.json）" % main)

    data: dict = {"apis": []}
    seen: set[str] = set()

    def _absorb(obj: object) -> None:
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict):
            items = obj.get("apis") or []
            for k, v in obj.items():
                if k != "apis":
                    data.setdefault(k, v)
        else:
            items = []
        for a in items:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            data["apis"].append(a)

    # 先完整文件，再分片（分片可补全文件里缺的条目）
    if main.is_file():
        _absorb(_read_json(main))
    for pf in parts:
        _absorb(_read_json(pf))

    data.setdefault("apis", [])
    if not data["apis"]:
        raise CatalogError("接口目录为空: %s" % main)
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
