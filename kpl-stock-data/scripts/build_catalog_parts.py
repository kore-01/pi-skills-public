#!/usr/bin/env python3
"""把 assets/apis.json 切成分片（assets/apis.partNN.json），绕开单文件体积限制。

为什么需要它
------------
部分安装环境对**单文件体积**有限制。`apis.json` 约 128 KB，会导致整个技能导入
被中断（表现：只落了 SKILL.md，references/ 和 scripts/ 全部丢失）。

本脚本按**完整 JSON 条目**边界切分，每个分片是一个合法 JSON 数组；
`kpls.catalog.load()` 会自动读取并合并所有分片，无需改任何调用方代码。

用法（Windows / 任意平台）
-------------------------
    python scripts/build_catalog_parts.py            # 默认切 24 KB/片
    python scripts/build_catalog_parts.py --size 16   # 更小的分片
    python scripts/build_catalog_parts.py --verify     # 合并后与原文件对比条目数

产物
----
    assets/apis.part00.json
    assets/apis.part01.json
    ...

原 `apis.json` **保留不动**（catalog 会自动合并并按 id 去重）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS = SKILL_DIR / "assets"
SOURCE = ASSETS / "apis.json"
DEFAULT_SIZE = 24 * 1024


def build(size: int) -> list[Path]:
    if not SOURCE.is_file():
        raise SystemExit("源文件不存在: %s" % SOURCE)

    raw = SOURCE.read_text(encoding="utf-8")
    data = json.loads(raw)
    apis = data.get("apis") or []
    if not apis:
        raise SystemExit("apis 数组为空: %s" % SOURCE)

    # 清掉旧分片，避免残留
    for old in ASSETS.glob("apis.part*.json"):
        old.unlink()

    parts: list[list[dict]] = []
    cur: list[dict] = []
    cur_len = 2  # '[]'
    for api in apis:
        blob = json.dumps(api, ensure_ascii=False, indent=2)
        add = len(blob) + 2  # 逗号 + 换行
        if cur and cur_len + add > size:
            parts.append(cur)
            cur, cur_len = [], 2
        cur.append(api)
        cur_len += add
    if cur:
        parts.append(cur)

    written: list[Path] = []
    for index, group in enumerate(parts):
        path = ASSETS / ("apis.part%02d.json" % index)
        path.write_text(json.dumps(group, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def verify() -> bool:
    """合并分片后与原文件逐条对比。"""
    if not SOURCE.is_file():
        raise SystemExit("源文件不存在: %s" % SOURCE)
    original = json.loads(SOURCE.read_text(encoding="utf-8")).get("apis") or []
    merged: list[dict] = []
    seen: set[str] = set()
    for path in sorted(ASSETS.glob("apis.part*.json")):
        for api in json.loads(path.read_text(encoding="utf-8")):
            aid = str(api.get("id") or "")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            merged.append(api)

    ok = len(merged) == len(original) and [a.get("id") for a in merged] == [a.get("id") for a in original]
    print("原始条目 : %d" % len(original))
    print("合并条目 : %d" % len(merged))
    print("分片数   : %d" % len(list(ASSETS.glob("apis.part*.json"))))
    print("结论     : %s" % ("一致 ✓" if ok else "不一致 ✗"))
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="切分 apis.json 为分片。")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="每片字节上限（默认 24576）")
    parser.add_argument("--verify", action="store_true", help="只做一致性校验")
    args = parser.parse_args(argv)

    if args.verify:
        return 0 if verify() else 1

    written = build(max(args.size, 2048))
    print("已写出 %d 个分片到 %s" % (len(written), ASSETS))
    for path in written:
        print("  %-28s %6d B" % (path.name, path.stat().st_size))
    print()
    print("校验：")
    verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
