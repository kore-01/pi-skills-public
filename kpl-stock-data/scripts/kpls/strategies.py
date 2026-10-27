# -*- coding: utf-8 -*-
"""kpls.strategies — 策略选股。

Tier1（本地多源，随时可用）：开盘啦官方 + 东财 + 新浪 + Tushare + L2 → 本地指标/策略
Tier2（平台已建策略，需 py.590 Token）：erjin3 / sanjin4 / sijin5 / lbc5plus / 困境反转 /
首板点火 / 竞价委买池 / 天梯看板 / 综合选择 / 一字低吸池 ...
"""
from __future__ import annotations

import re
import time
from statistics import fmean

from . import em, indicators, kpl, l2, py590, sn, ts

# Tier2：平台已建好的策略（需 Token；月卡/年卡门禁在服务端）
PLATFORM_STRATEGIES: dict[str, str] = {
    "strategy_overview": "strategy_overview",
    "erjin3": "erjin3_board",
    "sanjin4": "sanjin4_board",
    "sijin5": "sijin5_board",
    "lbc5plus": "lbc5plus_board",
    "weimai_buy_pool": "weimai_buy_pool",
    "weimai_morning_bidding": "weimai_morning_bidding",
    "weimai_strategy_pool": "weimai_strategy_pool",
    "distress_reversal": "distress_reversal_board",
    "firstboard_ignite": "firstboard_ignite_board",
    "ladder_board": "ladder_board",
    "broken_board": "broken_stocks",
    "composite": "composite-select/board",
    "surge_lowbuy": "surge-lowbuy-pool",
    "quant_pools": "ladder/quant_pools",
    "ladder_watch": "ladder/watch",
    "ladder_watch_l2": "ladder/watch_l2",
    "auction_pool": "auction-pool",
    "mood_board": "mood/board",
    "zt_timeline": "zt-timeline/board",
    "l2_desk": "l2-desk",
    "l2_brief": "l2-brief",
    "darktrade_fund": "darktrade-fund/board",
    "em_fflow": "em-fflow/board",
    "ths_bigorder": "ths-bigorder/board",
    "kanpan": "kanpan/board",
    "popularity": "popularity/board",
}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _pct(v) -> float | None:
    """小数比例 → 百分数（0.0998 → 9.98）。仅用于选股宝等返回小数的字段。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f * 100, 4)


def _hhmmss(v) -> str | None:
    """epoch 秒 → 'HHMMSS'；已是 6 位数字串则原样。"""
    s = str(v or "").strip()
    if s.isdigit() and len(s) == 6:
        return s
    try:
        ts = int(float(s))
    except (TypeError, ValueError):
        return None
    return time.strftime("%H%M%S", time.localtime(ts)) if ts > 10 ** 8 else None


def _diag_ok() -> bool:
    return bool(config_token())


def config_token() -> str:
    from . import config
    return config.py_token()


# ---------------------------------------------------------------- 候选池
def kpl_zt_pool(*, pid_type: str = "1") -> list[dict]:
    """开盘啦官方涨停池（daily_limit_realtime；info 首行为表头，非股票行自动跳过）。"""
    data = kpl.call("daily_limit_realtime", {"PidType": pid_type})
    out: list[dict] = []
    for r in kpl.rows(data):
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            code = str(r[0]).strip().zfill(6)
            if not code.isdigit():
                continue
            out.append({"code": code, "name": str(r[1]), "source": "kpl_zt"})
        elif isinstance(r, dict):
            code = str(r.get("code") or r.get("StockID") or "").strip().zfill(6)
            if code.isdigit() and len(code) == 6:
                out.append({"code": code, "name": r.get("name") or r.get("Name"),
                            "source": "kpl_zt"})
    return out


def xgb_zt_pool() -> list[dict]:
    """选股宝涨停池（经开盘啦接口 limit_up_realtime，含连板数/封单/换手）。"""
    data = kpl.call("limit_up_realtime")
    rows = data.get("data") if isinstance(data, dict) else None
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = str(r.get("symbol") or r.get("code") or r.get("stock_id")
                   or r.get("StockID") or "").split(".")[0].strip().zfill(6)
        if not code.isdigit() or len(code) != 6:
            continue
        plate = r.get("plate") if isinstance(r.get("plate"), dict) else {}
        rel = (plate.get("related_plates") or [{}])
        rel0 = rel[0] if rel and isinstance(rel[0], dict) else {}
        out.append({
            "code": code,
            "name": r.get("stock_chi_name") or r.get("name") or r.get("StockName"),
            "price": r.get("latest") or r.get("price"),
            "pct_chg": _pct(r.get("change_percent")),
            "boards": r.get("limit_up_days"),
            "turnover": _pct(r.get("turnover_ratio")),
            "amount": r.get("amount") or r.get("turnover"),
            "seal_amount": r.get("buy_lock_volume") or r.get("lock_amount")
            or r.get("seal_amount"),
            "first_seal": _hhmmss(r.get("first_limit_up")),
            "last_seal": _hhmmss(r.get("last_limit_up")),
            "plate": rel0.get("plate_name") or plate.get("plate_name"),
            "reason": (plate.get("stock_reason") or "")[:80] or None,
            "source": "xgb_zt",
        })
    return out


def universe(*, codes: list[str] | None = None, source: str = "em_all", limit: int = 200,
             fid: str = "f3") -> list[dict]:
    """候选池。codes 优先；否则按 source 取。

    source: em_all(涨幅榜) / em_turnover / em_main(主力净额) / em_amount /
            sn_amount / sn_change / sn_turnover（新浪排行）/
            zt(东财涨停池→开盘啦兜底) / kpl_zt(开盘啦) / xgb_zt(选股宝)。
    东财 push2 族不可达时自动降级为新浪排行（main_net 置 None）。
    """
    if codes:
        return [{"code": str(c).zfill(6), "name": "", "source": "explicit"} for c in codes]
    if source in ("zt", "kpl_zt", "xgb_zt"):
        if source == "kpl_zt":
            return kpl_zt_pool()
        if source == "xgb_zt":
            return xgb_zt_pool()
        try:
            rows = em.zt_pool()
            if rows:
                return rows
        except Exception:  # noqa: BLE001
            pass
        return kpl_zt_pool()
    if source.startswith("sn_"):
        sn_sort = {"sn_amount": "amount", "sn_change": "changepercent",
                   "sn_turnover": "turnoverratio"}.get(source, "changepercent")
        return sn.rank(sort=sn_sort, num=min(max(limit, 1), 100))
    fid_map = {"em_turnover": "f8", "em_main": "f62", "em_amount": "f6", "em_all": fid}
    try:
        rows = em.clist(fid=fid_map.get(source, fid), pz=limit, po=1)
        if rows:
            return rows
    except Exception:  # noqa: BLE001
        pass
    sn_sort = {"em_turnover": "turnoverratio", "em_main": "amount",
               "em_amount": "amount", "em_all": "changepercent"}.get(source, "changepercent")
    return sn.rank(sort=sn_sort, num=min(max(limit, 1), 100))


def snapshot(code: str, *, bars: int = 160, name: str = "", with_ts: bool = False) -> dict:
    """单标的快照：东财(实时+日线) → 新浪(兜底) → Tushare(可选复权/筹码)。"""
    src = "eastmoney"
    try:
        kl = em.bars(code, bars)
    except Exception:  # noqa: BLE001
        src, kl = "sina", sn.bars(code, bars)
    ind = indicators.compute(kl, code=code, name=name)
    ind["data_source"] = src
    if with_ts:
        try:
            ind["ts_factor"] = (ts.stk_factor(code) or [{}])[-1]
        except Exception:  # noqa: BLE001
            ind["ts_factor"] = {}
    return ind


def scan_candidates(cands: list[dict], *, bars: int = 160, min_score: int = 0, extra=None,
                    limit: int = 50) -> dict:
    """对候选池逐个算指标 → 过滤 → 按 score 排序（最多 limit 只）。"""
    out, errs = [], []
    for c in cands[:max(limit, 1) * 3]:
        code = str(c.get("code") or c.get("symbol") or "").zfill(6)
        if not code:
            continue
        try:
            ind = snapshot(code, bars=bars, name=str(c.get("name") or ""))
        except Exception as e:  # noqa: BLE001
            errs.append("%s: %s" % (code, e))
            continue
        if ind.get("score", 0) < min_score:
            continue
        for k in ("pct_chg", "main_net", "main_pct", "turnover", "circ_mv", "industry"):
            if c.get(k) is not None:
                ind.setdefault(k, c[k])
        if extra:
            extra(ind, c)
        out.append(ind)
        if len(out) >= limit:
            break
    out.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"count": len(out), "rows": out, "errors": errs}


# ---------------------------------------------------------------- Tier1 策略
def s_zt_pool(*, mode: str = "em", day: str | None = None, limit: int = 200, **kw) -> dict:
    """涨停池：em=东财涨停池；kpl=开盘啦官方 daily_limit_realtime（无表头，按列位映射）。"""
    if mode == "kpl":
        data = kpl.call("daily_limit_history" if day else "daily_limit_realtime",
                        {"Date": day} if day else {}, **kw)
        rows = kpl.table(data, cols=kpl.KPL_ZT_COLS)[:limit]
        for r in rows:
            r["boards"] = _boards_from_text(r.get("boards_text"))
    else:
        rows = em.zt_pool(day)[:limit]
    return {"strategy": "zt_pool", "mode": mode, "day": day or time.strftime("%Y%m%d"),
            "count": len(rows), "rows": rows,
            "sources": ["eastmoney"] if mode != "kpl" else ["kpl"], "at": _now()}


def _boards_from_text(text) -> int | None:
    """从「3天2板」这类文案解析连板数。"""
    m = re.search(r"(\d+)\s*板", str(text or ""))
    return int(m.group(1)) if m else None


def s_first_board(*, day: str | None = None, min_seal: float = 0.0, limit: int = 60) -> dict:
    """首板池：连板数=1 且封单额达标（东财涨停池口径 lbc）。"""
    pool = em.zt_pool(day)
    rows = [r for r in pool if int(r.get("boards") or 0) == 1 and float(r.get("seal_amount") or 0) >= min_seal]
    rows.sort(key=lambda r: float(r.get("seal_amount") or 0), reverse=True)
    for r in rows:
        r["first_seal"] = r.get("first_seal")
        r["tag"] = "首板"
    return {"strategy": "first_board", "day": day, "count": len(rows[:limit]), "rows": rows[:limit],
            "sources": ["eastmoney"], "at": _now()}


def s_ladder(*, day: str | None = None, min_boards: int = 2, limit: int = 80) -> dict:
    """连板天梯（东财涨停池按连板数分层；Tier2 可用 ladder_board 拿平台天梯）。"""
    pool = em.zt_pool(day)
    layers: dict[int, list] = {}
    for r in pool:
        lb = int(r.get("boards") or 0)
        if lb >= min_boards:
            layers.setdefault(lb, []).append(r)
    ordered = [{"boards": k, "count": len(v), "rows": v} for k, v in sorted(layers.items(), reverse=True)]
    flat = [r for g in ordered for r in g["rows"]][:limit]
    return {"strategy": "ladder", "day": day, "layers": ordered, "count": len(flat), "rows": flat,
            "sources": ["eastmoney"], "at": _now()}


def s_broken(*, day: str | None = None, min_open: int = 1, limit: int = 60) -> dict:
    """炸板回落池（东财炸板池 + 可选开盘啦炸板）。"""
    rows = [r for r in em.break_pool(day) if int(r.get("open_times") or 0) >= min_open]
    rows.sort(key=lambda r: int(r.get("open_times") or 0), reverse=True)
    return {"strategy": "broken", "day": day, "count": len(rows[:limit]), "rows": rows[:limit],
            "sources": ["eastmoney"], "at": _now()}


def s_auction_strong(*, top: int = 20, list_type: str = "4", **kw) -> dict:
    """竞价强势（开盘啦涨停委买额主池，按委买额排序）。"""
    data = kpl.call("morning_bidding_realtime", {"Type": list_type, "st": "200", **kw})
    rows = kpl.rows(data)
    parsed = []
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 9:
            parsed.append({"code": str(r[0]).zfill(6), "name": r[1], "pct_chg": r[2], "wme": r[3],
                           "jjzf": r[4], "jjje": r[5], "jjhs": r[6], "jjcje": r[7], "lb": r[8]})
        elif isinstance(r, dict):
            parsed.append(r)
    parsed.sort(key=lambda x: float(x.get("wme") or 0), reverse=True)
    return {"strategy": "auction_strong", "count": len(parsed[:top]), "rows": parsed[:top],
            "sources": ["kpl"], "at": _now()}


SINA_INDICES = (("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指"),
                ("sh000300", "沪深300"), ("sz399005", "中小100"))


def _sina_indices() -> list[dict]:
    """新浪指数快照兜底（东财市场总览不可达时）。"""
    try:
        rows = sn.quote([s for s, _ in SINA_INDICES])
    except Exception:  # noqa: BLE001
        return []
    names = dict(SINA_INDICES)
    out = []
    for r in rows:
        sym = str(r.get("symbol") or "")
        out.append({"code": sym[2:] if len(sym) > 2 else sym,
                    "name": names.get(sym) or r.get("name"),
                    "price": r.get("price"), "pct_chg": r.get("pct_chg"),
                    "change": r.get("change"), "amount": r.get("amount"),
                    "source": "sina"})
    return out


def s_emotion(**kw) -> dict:
    """情绪周期：涨停/炸板/跌停家数 + 开盘啦情绪值 + 涨跌家数。"""
    out: dict = {"strategy": "emotion", "sources": [], "at": _now()}
    try:
        out["zt"] = len(em.zt_pool())
        out["zb"] = len(em.break_pool())
        out["sources"].append("eastmoney")
    except Exception as e:  # noqa: BLE001
        out["zt_error"] = str(e)
    try:
        data = kpl.call("mood_num", kw or None)
        out["kpl_mood"] = kpl.rows(data) or data
        out["sources"].append("kpl")
    except Exception as e:  # noqa: BLE001
        out["mood_error"] = str(e)
    try:
        data = kpl.call("rise_fall_realtime", kw or None)
        out["rise_fall"] = kpl.rows(data) or data
    except Exception as e:  # noqa: BLE001
        out["rise_fall_error"] = str(e)
    zt, zb = out.get("zt"), out.get("zb")
    if zt is not None and zb is not None:
        out["seal_rate"] = round(zt / (zt + zb) * 100, 2) if (zt + zb) else None
    # 指数：东财市场总览 → 失败/为空则回落新浪指数快照
    out["indices"] = []
    try:
        out["indices"] = em.market_overview().get("indices") or []
    except Exception:  # noqa: BLE001
        pass
    if not out["indices"]:
        out["indices"] = _sina_indices()
    return out


def s_low_buy(*, limit: int = 120, min_zt: int = 1, ma: int = 5, tol: float = 0.012,
              max_vol_ratio: float = 1.0, bars: int = 160) -> dict:
    """低吸：涨幅榜候选 → 回踩 MA5/MA10 附近 + 缩量 + 有涨停基因。"""
    cands = universe(source="em_all", limit=limit)
    res: list[dict] = []
    errs: list[str] = []
    for c in cands:
        code = str(c.get("code") or "").zfill(6)
        try:
            ind = snapshot(code, bars=bars, name=str(c.get("name") or ""))
        except Exception as e:  # noqa: BLE001
            errs.append("%s: %s" % (code, e))
            continue
        lim = ind.get("limit") or {}
        if (lim.get("zt_count") or 0) < min_zt:
            continue
        pb = ind.get("pullback_ma5") or {}
        if not (pb.get("ok") or abs(pb.get("dist_pct") or 99) <= tol * 100):
            continue
        vr = ind.get("vol_ratio5")
        if vr is not None and vr > max_vol_ratio:
            continue
        ind["pct_chg_today"] = ind.get("pct_chg")
        ind["src_pct"] = c.get("pct_chg")
        res.append(ind)
    res.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"strategy": "low_buy", "count": len(res), "rows": res, "errors": errs,
            "sources": ["eastmoney", "sina"], "at": _now()}


def s_breakout(*, limit: int = 120, bars: int = 160, min_vol_ratio: float = 1.2) -> dict:
    """平台突破：候选池 → 20 日新高 + 放量。"""
    cands = universe(source="em_all", limit=limit)
    res = []
    for c in cands:
        code = str(c.get("code") or "").zfill(6)
        try:
            ind = snapshot(code, bars=bars, name=str(c.get("name") or ""))
        except Exception:  # noqa: BLE001
            continue
        bo = ind.get("breakout20") or {}
        if bo.get("ok") and (bo.get("vol_ratio") or 0) >= min_vol_ratio:
            res.append(ind)
    res.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"strategy": "breakout", "count": len(res), "rows": res,
            "sources": ["eastmoney"], "at": _now()}


def s_main_inflow(*, limit: int = 60, min_net: float = 0.0, with_flow: bool = False) -> dict:
    """主力资金流入（东财 f62 排行；EM 不可达时降级为新浪成交额榜并标注）。"""
    src = "eastmoney"
    try:
        rows = em.clist(fid="f62", pz=limit, po=1)
    except Exception:  # noqa: BLE001
        src, rows = "sina-rank", sn.rank(sort="amount", num=min(max(limit, 1), 100))
    if src == "eastmoney":
        rows = [r for r in rows if (r.get("main_net") or 0) > min_net]
    if with_flow and src == "eastmoney":
        for r in rows[:20]:
            try:
                f = em.fflow(r["code"], lmt=5, klt=0)
                r["flow5"] = [x["main_net"] for x in f["series"]]
            except Exception as e:  # noqa: BLE001
                r["flow_error"] = str(e)
    out = {"strategy": "main_inflow", "count": len(rows[:limit]), "rows": rows[:limit],
           "sources": [src], "at": _now()}
    if src != "eastmoney":
        out["note"] = "东财 push2 不可达，已降级为新浪成交额榜（该源无主力净额字段）"
    return out


def s_lhb(*, day: str | None = None, limit: int = 60, **kw) -> dict:
    """龙虎榜：开盘啦官方列表（Tushare top_inst/hm_detail 作交叉验证）。"""
    out: dict = {"strategy": "lhb", "day": day, "sources": [], "at": _now()}
    try:
        data = kpl.call("longhubang_list", {"Date": day} if day else {}, **kw)
        out["rows"] = kpl.rows(data)[:limit]
        out["sources"].append("kpl")
    except Exception as e:  # noqa: BLE001
        out["kpl_error"] = str(e)
    try:
        d = (day or "").replace("-", "") or ts.last_trade_day()
        out["top_inst"] = ts.top_inst(d)[:limit]
        out["sources"].append("tushare")
    except Exception as e:  # noqa: BLE001
        out["tushare_error"] = str(e)
    out["count"] = len(out.get("rows") or [])
    return out


def s_multi_confirm(*, top: int = 20, bars: int = 160, min_main_net: float = 0.0,
                    limit: int | None = None, **kw) -> dict:
    """多源共振：涨停池（东财→选股宝→开盘啦）∩ 主力净额>0 ∩ 本地指标打分。"""
    top = int(limit or top)
    src_zt = "eastmoney"
    try:
        zt = em.zt_pool()
    except Exception:  # noqa: BLE001
        zt = []
    if not zt:
        src_zt, zt = "xgb", xgb_zt_pool()
    if not zt:
        src_zt, zt = "kpl", kpl_zt_pool()
    codes = [str(r["code"]).zfill(6) for r in zt[:max(top * 3, 30)]]
    if not codes:
        return {"strategy": "multi_confirm", "count": 0, "rows": [], "at": _now()}
    snap: dict = {}
    src_flow = "eastmoney"
    try:
        snap = {r.get("code"): r for r in em.ulist(codes)}
    except Exception:  # noqa: BLE001
        src_flow = "sina"
        try:
            snap = {r.get("code"): r for r in sn.quote(codes)}
        except Exception:  # noqa: BLE001
            snap = {}
    rows = []
    for r in zt:
        code = str(r["code"]).zfill(6)
        q = snap.get(code) or {}
        if min_main_net and (q.get("main_net") or 0) < min_main_net:
            continue
        try:
            ind = snapshot(code, bars=bars, name=str(r.get("name") or ""))
        except Exception:  # noqa: BLE001
            continue
        ind["main_net"] = q.get("main_net")
        ind["main_pct"] = q.get("main_pct")
        ind["turnover"] = q.get("turnover") or r.get("turnover")
        ind["boards"] = r.get("boards")
        ind["seal_amount"] = r.get("seal_amount")
        ind["confirmed"] = ["zt-%s" % src_zt, "flow-%s" % src_flow]
        if (ind.get("score") or 0) >= 60:
            ind["confirmed"].append("indicator")
        rows.append(ind)
        if len(rows) >= top:
            break
    rows.sort(key=lambda x: (len(x.get("confirmed") or []), x.get("score", 0)), reverse=True)
    return {"strategy": "multi_confirm", "count": len(rows), "rows": rows,
            "sources": [src_zt, src_flow, "local-indicators"], "at": _now()}


def s_trend_pick(*, limit: int = 150, bars: int = 160, min_score: int = 60) -> dict:
    """趋势票：多头排列 + 站上 MA20 + 打分达标。"""
    cands = universe(source="em_turnover", limit=limit)
    res = []
    for c in cands:
        code = str(c.get("code") or "").zfill(6)
        try:
            ind = snapshot(code, bars=bars, name=str(c.get("name") or ""))
        except Exception:  # noqa: BLE001
            continue
        m = ind.get("ma") or {}
        if m.get("bull") and m.get("above_ma20") and (ind.get("score") or 0) >= min_score:
            res.append(ind)
    res.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"strategy": "trend_pick", "count": len(res), "rows": res,
            "sources": ["eastmoney"], "at": _now()}


def s_l2_strong(codes: list[str] | None = None, *, pool_limit: int = 20, money: int = 2) -> dict:
    """L2 主动大单净额为强的标的（开盘啦 L2 大单成交）。

    未指定 codes 时用成交额候选池（东财→新浪降级链）取前 pool_limit 只。
    """
    src = "explicit"
    if not codes:
        pool = universe(source="em_amount", limit=pool_limit)
        src = str(pool[0].get("source")) if pool else "empty"
        codes = [str(r.get("code") or "").zfill(6) for r in pool]
    rows = []
    for code in codes[:pool_limit]:
        try:
            m = l2.monitor(code, money=money, st=40)
        except Exception as e:  # noqa: BLE001
            rows.append({"code": code, "error": str(e)})
            continue
        rows.append({"code": code, "big_net": m["net"], "big_buy": m["active_buy"],
                     "big_sell": m["active_sell"], "orders": m["count"]})
    rows.sort(key=lambda r: r["big_net"], reverse=True)
    return {"strategy": "l2_strong", "count": len(rows), "rows": rows,
            "sources": ["kpl-l2"], "at": _now()}


def s_quote_compare(codes: list[str]) -> dict:
    """多源行情对照（开盘啦盘口 / 新浪 / 东财），用于交叉校验与排错。"""
    rows = []
    for code in codes:
        code = str(code).zfill(6)
        row: dict = {"code": code}
        try:
            pk = l2.pankou(code)
            row["kpl"] = {"real": pk.get("real"), "weibi": l2.summary({"pankou": pk}).get("weibi")}
        except Exception as e:  # noqa: BLE001
            row["kpl_error"] = str(e)
        try:
            q = sn.quote(code)[0]
            row["sina"] = {k: q.get(k) for k in ("name", "price", "pct_chg", "volume", "amount", "time")}
        except Exception as e:  # noqa: BLE001
            row["sina_error"] = str(e)
        try:
            q = em.quote(code)
            row["em"] = {k: (q.get("decoded") or {}).get(k) for k in ("name", "price", "pct_chg", "turnover", "main_net")}
        except Exception as e:  # noqa: BLE001
            row["em_error"] = str(e)
        rows.append(row)
    return {"strategy": "quote_compare", "count": len(rows), "rows": rows,
            "sources": ["kpl", "sina", "eastmoney"], "at": _now()}


TIER1 = {
    "zt_pool": (s_zt_pool, "涨停池（em 东财 / kpl 开盘啦）"),
    "first_board": (s_first_board, "首板池（连板=1 + 封单额）"),
    "ladder": (s_ladder, "连板天梯（按连板数分层）"),
    "broken": (s_broken, "炸板回落池"),
    "auction_strong": (s_auction_strong, "竞价强势（开盘啦涨停委买额）"),
    "emotion": (s_emotion, "情绪周期（涨停/炸板家数 + 情绪值）"),
    "low_buy": (s_low_buy, "低吸（回踩均线 + 缩量 + 涨停基因）"),
    "breakout": (s_breakout, "平台突破（20 日新高 + 放量）"),
    "main_inflow": (s_main_inflow, "主力资金流入（东财 f62 排行）"),
    "lhb": (s_lhb, "龙虎榜（开盘啦 + Tushare）"),
    "multi_confirm": (s_multi_confirm, "多源共振（涨停 ∩ 主力净额 ∩ 指标）"),
    "trend_pick": (s_trend_pick, "趋势票（多头排列 + 打分）"),
    "l2_strong": (s_l2_strong, "L2 主动大单净额强势"),
    "quote_compare": (s_quote_compare, "多源行情对照"),
}


def list_strategies() -> dict:
    return {
        "tier1": [{"name": k, "desc": v[1], "needs_token": False} for k, v in sorted(TIER1.items())],
        "tier2": [{"name": k, "endpoint": v, "needs_token": True} for k, v in sorted(PLATFORM_STRATEGIES.items())],
    }


def describe(name: str) -> dict:
    if name in TIER1:
        return {"name": name, "tier": 1, "desc": TIER1[name][1]}
    if name in PLATFORM_STRATEGIES:
        return {"name": name, "tier": 2, "endpoint": PLATFORM_STRATEGIES[name], "needs_token": True}
    return {"name": name, "error": "未知策略"}


def run(name: str, **kw) -> dict:
    """跑策略：Tier1 本地计算；Tier2 走平台（需 Token）。未知参数自动忽略（limit→top 别名）。"""
    if name in TIER1:
        fn = TIER1[name][0]
        kw = _fit_kwargs(fn, kw)
        return fn(**kw)
    if name in PLATFORM_STRATEGIES:
        ep = PLATFORM_STRATEGIES[name]
        if name == "strategy_overview":
            codes = kw.pop("codes", None)
            if codes:
                return py590.strategy_overview(codes, kw.pop("day", None))
        return py590.board(ep, kw or None)
    raise KeyError("未知策略 %s（可用: %s）" % (name, ", ".join(sorted(list(TIER1) + list(PLATFORM_STRATEGIES)))))


def _fit_kwargs(fn, kw: dict) -> dict:
    """按函数签名过滤参数；无 limit 形参时把 limit 映射为 top。"""
    import inspect as _inspect
    try:
        sig = _inspect.signature(fn)
    except (TypeError, ValueError):
        return kw
    params = sig.parameters
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return kw
    kw = dict(kw)
    if "limit" in kw and "limit" not in params and "top" in params:
        kw["top"] = kw.pop("limit")
    return {k: v for k, v in kw.items() if k in params}
