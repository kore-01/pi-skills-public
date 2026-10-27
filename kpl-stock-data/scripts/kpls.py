#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kpls - 股票数据 / 指标 / 策略选股 命令行。

用法示例：
  python kpls.py doctor                       # 全链路自检（配置 + 各源连通）
  python kpls.py accounts                     # 查看内置开盘啦账号（脱敏）
  python kpls.py catalog -q 竞价 --limit 10    # 查接口目录（152 条）
  python kpls.py api kline_day StockID=600519  # 通用调用（自动路由到数据源）
  python kpls.py kpl mood_num                  # 开盘啦官方
  python kpls.py l2 600519 --parts pankou,bid,monitor
  python kpls.py ts daily symbol=600519 start_date=20260101
  python kpls.py sn quote 600519
  python kpls.py em clist --fid f62 --pz 20    # 东财主力净额排行
  python kpls.py indicator 600519 --bars 160   # 本地指标
  python kpls.py strategy list
  python kpls.py strategy run low_buy --limit 60
  python kpls.py py ladder/board               # 平台看板（需 Token）
  python kpls.py quote 600519 000001           # 多源行情对照
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kpls import catalog, config, em, indicators, kpl, kore_mint, l2, py590, sn, strategies, ts  # noqa: E402


def _out(obj, *, limit: int = 0, keys: str = "") -> None:
    """输出 JSON；limit 截断 rows；keys 过滤字段（表格视图）。"""
    if isinstance(obj, dict) and limit and isinstance(obj.get("rows"), list):
        obj = dict(obj)
        obj["rows"] = obj["rows"][:limit]
    if keys and isinstance(obj, dict) and isinstance(obj.get("rows"), list):
        kk = [x.strip() for x in keys.split(",") if x.strip()]
        obj = dict(obj)
        obj["rows"] = [{k: r.get(k) for k in kk} for r in obj["rows"]]
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _kv(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit("参数需为 k=v 形式: %s" % p)
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _codes(raw: str | None) -> list[str]:
    return [c.strip() for c in (raw or "").replace("，", ",").split(",") if c.strip()]


# ---------------------------------------------------------------- 子命令
def cmd_doctor(args) -> int:
    info = config.doctor()
    print("== 配置 ==")
    print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
    print("\n== 数据源连通性 ==")
    checks: list[tuple[str, object]] = [
        ("kpl(开盘啦官方)", lambda: kpl.call("kline_day", {"StockID": "000001", "st": "3"})),
        ("kpl-account2", lambda: kpl.call("kline_day", {"StockID": "000001", "st": "3"}, account="account_8115")),
        ("l2(开盘啦L2)", lambda: l2.pankou("600519")),
        ("tushare", lambda: ts.daily(symbol="600519", start_date=ts.last_trade_day())[:1]),
        ("sina(新浪)", lambda: sn.quote("600519")),
        ("em(东方财富)", lambda: em.quote("600519")),
        ("em-zt(涨停池)", lambda: em.zt_pool()[:1]),
        ("py(平台双机health)", lambda: py590.health()),
        ("py-api(平台接口)", lambda: py590.call_path("/api/premarket/board")),
    ]
    bad = 0
    for name, fn in checks:
        try:
            res = fn()
            n = len(res) if isinstance(res, (list, tuple)) else ""
            print("  [OK]   %-22s %s" % (name, ("%s 条" % n) if n != "" else ""))
            if args.verbose:
                print("         " + json.dumps(res, ensure_ascii=False, default=str)[:400])
        except Exception as e:  # noqa: BLE001
            print("  [FAIL] %-22s %s" % (name, str(e).encode("utf-8", "replace").decode("utf-8")[:300]))
            bad += 1
    print("\n结论: %d/%d 通过" % (len(checks) - bad, len(checks)))
    return 0 if bad == 0 else 1


def cmd_accounts(args) -> int:
    _out([a.info() for a in config.accounts()])
    return 0


def cmd_catalog(args) -> int:
    rows = catalog.search(args.q or args.query_pos or "", domain=args.domain or "", category=args.category or "",
                          tag=args.tag or "", limit=args.limit)
    if args.full:
        _out(rows)
    else:
        _out([catalog.brief(a) for a in rows])
    print("共 %d 条（目录 %s）" % (len(rows), catalog.meta().get("generated_at", "?")), file=sys.stderr)
    return 0


def cmd_api(args) -> int:
    from kpls import router

    _out(router.call(args.api_id, _kv(args.params)))
    return 0


def cmd_kpl(args) -> int:
    _out(kpl.call(args.api_id, _kv(args.params)))
    return 0


def cmd_ts(args) -> int:
    params = _kv(args.params)
    fields = params.pop("fields", "")
    symbol = params.pop("symbol", None)
    if symbol and "ts_code" not in params:
        params["ts_code"] = ts.to_ts_code(symbol)
    _out(ts.pro(args.api_name, fields=fields, **params)[: args.limit or 0])
    return 0


def cmd_sn(args) -> int:
    if args.mode == "quote":
        _out(sn.quote(args.value))
    elif args.mode == "ulist":
        _out(sn.quote(_codes(args.value)))
    elif args.mode == "kline":
        _out(sn.kline(args.value, args.scale, args.datalen))
    elif args.mode == "codes":
        _out(sn.codes(args.node, args.limit or None))
    elif args.mode == "bars":
        _out(sn.bars(args.value, args.datalen))
    elif args.mode == "rank":
        _out(sn.rank(args.node, sort=args.sort, asc=args.asc, num=args.limit or 80))
    return 0


def cmd_em(args) -> int:
    if args.mode == "quote":
        _out(em.quote(args.value))
    elif args.mode == "ulist":
        _out(em.ulist(_codes(args.value)))
    elif args.mode == "kline":
        _out(em.kline(args.value, klt=args.klt, fqt=args.fqt, lmt=args.datalen,
                      beg=args.beg, end=args.end))
    elif args.mode == "clist":
        _out(em.clist(fs=args.fs, fid=args.fid, po=args.po, pn=args.pn, pz=args.pz))
    elif args.mode == "fflow":
        _out(em.fflow(args.value, lmt=args.datalen, klt=args.klt))
    elif args.mode == "zt":
        _out(em.zt_pool(args.date))
    elif args.mode == "zb":
        _out(em.break_pool(args.date))
    elif args.mode == "market":
        _out(em.market_overview())
    return 0


def cmd_l2(args) -> int:
    parts = tuple(p.strip() for p in (args.parts or "pankou,bid,monitor").split(",") if p.strip())
    kw = {"money": args.money} if "monitor" in parts else {}
    if "chouma" in parts and args.day:
        _out(l2.pack(args.code, parts, day=args.day, **kw))
    else:
        _out(l2.pack(args.code, parts, **kw))
    return 0


def cmd_py(args) -> int:
    params = _kv(args.params)
    _out(py590.board(args.endpoint, params or None))
    return 0


def cmd_py_health(args) -> int:
    _out(py590.health())
    return 0


def cmd_py_list(args) -> int:
    rows = py590.list_apis()
    _out(rows[: args.limit] if args.limit else rows)
    return 0


def cmd_py_export(args) -> int:
    _out(py590.export_token(args.kore_token))
    return 0



def cmd_kore_mint(args) -> int:
    """铸造长效 Kore token（可选授权/镜像/校验）。"""
    return kore_mint.main(args)

def _bars_multi(code: str, n: int, adj: bool = False):
    """按 em → sn → ts 顺序取 K 线，任一可用即返回 (源名, bars)。"""
    errs = []
    for name, fn in (
        ("em", lambda: em.bars(code, n)),
        ("sn", lambda: sn.bars(code, n)),
        ("ts", lambda: ts.bars(code, n, adj=adj)),
    ):
        try:
            bars = fn()
            if bars:
                return name, bars
            errs.append("%s: 空" % name)
        except Exception as exc:  # noqa: BLE001
            errs.append("%s: %s" % (name, exc))
    raise RuntimeError("K线多源均失败 -> " + "; ".join(errs))


def cmd_indicator(args) -> int:
    if getattr(args, "list_mode", False) or args.code in ("", "list", "ls", "-l", "--list"):
        _out({"ok": True, "indicators": indicators.CATALOG,
              "hint": "kpls indicator <code> [--source auto|em|sn|ts] [--bars 160] [--adj]"})
        return 0
    src = args.source
    if src == "auto":
        src, bars = _bars_multi(args.code, args.bars, adj=args.adj)
    elif src == "ts":
        bars = ts.bars(args.code, args.bars, adj=args.adj)
    elif src == "sn":
        bars = sn.bars(args.code, args.bars)
    else:
        bars = em.bars(args.code, args.bars)
    ind = indicators.compute(bars, code=args.code, name=args.name or "")
    ind["bars"] = len(bars)
    ind["data_source"] = src
    _out(ind)
    return 0


def cmd_strategy(args) -> int:
    if args.action == "list":
        _out(strategies.list_strategies())
        return 0
    if args.action == "run":
        codes = _codes(args.codes)
        kw = _kv(args.params)
        for k in ("limit", "top", "bars", "min_zt", "min_score", "money", "pool_limit"):
            if k in kw:
                kw[k] = int(kw[k])
        if codes and args.name in ("quote_compare",):
            kw["codes"] = codes
        elif args.name in ("strategy_overview",):
            kw["codes"] = codes
        elif codes and args.name in strategies.TIER1:
            kw["codes"] = codes
        _out(strategies.run(args.name, **kw), limit=args.limit)
        return 0
    raise SystemExit("未知动作: %s" % args.action)


def cmd_quote(args) -> int:
    _out(strategies.s_quote_compare([c for arg in args.codes for c in _codes(arg)]))
    return 0


def cmd_test(args) -> int:
    """快速实盘取数测试（无需 Token）：≥3 个数据源 + L2 + 本地指标。"""
    from kpls import router

    hits = 0
    checks = [
        ("kpl.kline_day", lambda: kpl.call("kline_day", {"StockID": args.code, "st": "30"})),
        ("kpl.mood_num", lambda: kpl.call("mood_num", {})),
        ("router.api(kline_day)", lambda: router.call("kline_day", {"StockID": args.code, "st": "10"})),
        ("ts.daily", lambda: ts.daily(symbol=args.code, start_date=ts.last_trade_day())),
        ("sn.quote", lambda: sn.quote(args.code)),
        ("em.zt_pool", lambda: em.zt_pool()),
        ("l2.pankou", lambda: l2.pankou(args.code)),
        ("indicators.compute", lambda: indicators.compute(_bars_multi(args.code, 120)[1],
                                                         code=args.code)),
    ]
    for name, fn in checks:
        try:
            res = fn()
            n = len(res) if isinstance(res, (list, tuple)) else "-"
            print("[OK]   %-24s items=%s" % (name, n))
            hits += 1
        except Exception as e:  # noqa: BLE001
            print("[FAIL] %-24s %s" % (name, str(e)[:200]))
    print("通过 %d/%d" % (hits, len(checks)))
    return 0 if hits >= 3 else 1


# ---------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kpls", description="股票数据 / 指标 / 策略选股（开盘啦+Tushare+新浪+东财+L2+平台）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="全链路自检")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_doctor)

    sub.add_parser("accounts", help="查看内置开盘啦账号（脱敏）").set_defaults(fn=cmd_accounts)

    p = sub.add_parser("catalog", help="接口目录（152 条）")
    p.add_argument("-q", "--query", dest="q", default=None)
    p.add_argument("query_pos", nargs="?", default=None)
    p.add_argument("--domain")
    p.add_argument("--category")
    p.add_argument("--tag")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--full", action="store_true", help="输出完整条目")
    p.set_defaults(fn=cmd_catalog)

    p = sub.add_parser("api", help="通用调用（自动路由）")
    p.add_argument("api_id")
    p.add_argument("params", nargs="*")
    p.set_defaults(fn=cmd_api)

    p = sub.add_parser("kpl", help="开盘啦官方接口")
    p.add_argument("api_id")
    p.add_argument("params", nargs="*")
    p.set_defaults(fn=cmd_kpl)

    p = sub.add_parser("ts", help="Tushare Pro")
    p.add_argument("api_name")
    p.add_argument("params", nargs="*")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_ts)

    p = sub.add_parser("sn", help="新浪")
    p.add_argument("mode", choices=["quote", "ulist", "kline", "codes", "bars", "rank"])
    p.add_argument("value", nargs="?", default="")
    p.add_argument("--scale", default="240")
    p.add_argument("--datalen", type=int, default=240)
    p.add_argument("--node", default="hs_a")
    p.add_argument("--sort", default="amount")
    p.add_argument("--asc", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_sn)

    p = sub.add_parser("em", help="东方财富")
    p.add_argument("mode", choices=["quote", "ulist", "kline", "clist", "fflow", "zt", "zb", "market"])
    p.add_argument("value", nargs="?", default="")
    p.add_argument("--klt", type=int, default=101)
    p.add_argument("--fqt", type=int, default=1)
    p.add_argument("--datalen", type=int, default=240)
    p.add_argument("--beg")
    p.add_argument("--end")
    p.add_argument("--fs", default=em.FS_ALL_A)
    p.add_argument("--fid", default="f3")
    p.add_argument("--po", type=int, default=1)
    p.add_argument("--pn", type=int, default=1)
    p.add_argument("--pz", type=int, default=30)
    p.add_argument("--date")
    p.set_defaults(fn=cmd_em)

    p = sub.add_parser("l2", help="开盘啦 L2 件套")
    p.add_argument("code")
    p.add_argument("--parts", default="pankou,bid,monitor")
    p.add_argument("--money", type=int, default=2)
    p.add_argument("--day")
    p.set_defaults(fn=cmd_l2)

    p = sub.add_parser("py", help="平台看板/策略端点（需 Token）")
    p.add_argument("endpoint")
    p.add_argument("params", nargs="*")
    p.set_defaults(fn=cmd_py)

    sub.add_parser("py-health", help="平台双机 /health").set_defaults(fn=cmd_py_health)

    p = sub.add_parser("py-list", help="平台 /api/list（需 Token）")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_py_list)

    p = sub.add_parser("py-export", help="Kore JWT → 当日 scoped token 并保存")
    p.add_argument("--kore-token", dest="kore_token", required=True)
    p.set_defaults(fn=cmd_py_export)
    p = sub.add_parser("kore-mint", help="铸造长效 Kore Token（+授权/镜像/校验）")
    p.add_argument("--secret", default="", help="JWT_SECRET（默认读环境变量 KORE_JWT_SECRET）")
    p.add_argument("--from-ssh", dest="from_ssh", action="store_true", help="经 SSH 从 212 机 .env 读取 JWT_SECRET")
    p.add_argument("--user-id", dest="user_id", type=int, default=1)
    p.add_argument("--username", default="e07559")
    p.add_argument("--role", default="admin")
    p.add_argument("--exp", type=int, default=4102444800, help="到期秒级时间戳（默认 2100-01-01）")
    p.add_argument("--out", default="", help="输出文件（默认 assets/py_token.txt）")
    p.add_argument("--grant-all", dest="grant_all", action="store_true", help="按 assets/features.lifetime.txt 全量授权")
    p.add_argument("--features", default="", help="自定义授权清单（逗号分隔）")
    p.add_argument("--mirror", action="store_true", help="把主机权益镜像到备机 55（双机一致）")
    p.add_argument("--verify", action="store_true", help="校验四域名权益与 /api/list")
    p.add_argument("--check", action="store_true", help="只读体检 Token/权益/两机（不写库；不健康退出码 2）")
    p.add_argument("--auto", action="store_true", help="体检不通过才自动轮换（定时任务入口；健康则零写入）")
    p.set_defaults(fn=cmd_kore_mint)

    p = sub.add_parser("indicator", help="本地指标")
    p.add_argument("code", nargs="?", default="")
    p.add_argument("-l", "--list", dest="list_mode", action="store_true", help="列出内置指标清单")
    p.add_argument("--bars", type=int, default=160)
    p.add_argument("--source", choices=["auto", "em", "sn", "ts"], default="auto")
    p.add_argument("--adj", action="store_true")
    p.add_argument("--name", default="")
    p.set_defaults(fn=cmd_indicator)

    p = sub.add_parser("strategy", help="策略选股")
    p.add_argument("action", choices=["list", "run"])
    p.add_argument("name", nargs="?")
    p.add_argument("params", nargs="*")
    p.add_argument("--codes")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(fn=cmd_strategy)

    p = sub.add_parser("quote", help="多源行情对照")
    p.add_argument("codes", nargs="+")
    p.set_defaults(fn=cmd_quote)

    p = sub.add_parser("test", help="快速实盘取数测试（免 Token）")
    p.add_argument("--code", default="600519")
    p.set_defaults(fn=cmd_test)

    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
