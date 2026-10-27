# -*- coding: utf-8 -*-
"""kpls.l2 — 开盘啦 L2（apphwhq/apphq）：竞价分时、盘口五档、大单成交、大单委托、筹码、分时。

方向编码（开盘啦官方）：
  main_monitor 买卖方：1 被动卖 / 2 主动买 / 3 被动买 / 4 主动卖
  stock_bid / stock_trend 的方向字段：1 买 / 2 卖（或 0 中性，容错处理）
成功判定用 `data["errcode"] == "0"`；`code` 字段是股票代码字符串，不是错误码。
"""
from __future__ import annotations

from . import http, kpl

PARTS = ("pankou", "bid", "trend", "monitor", "weituo", "chouma", "dadan")


def _num(v) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _pick(row, idx: int, *names, default=0):
    """兼容 list-of-list 与 list-of-dict 两种上游形态。"""
    if isinstance(row, dict):
        for n in names:
            if n in row and row[n] not in (None, ""):
                return row[n]
        return default
    if isinstance(row, (list, tuple)) and len(row) > idx:
        return row[idx]
    return default


def _rows(data) -> list:
    return kpl.rows(data)


def pankou(code: str, **kw) -> dict:
    """盘口：real（现价/涨幅/换手/市值）+ weituo 五档（b1..b10/s1..s10）。"""
    data = kpl.call("pankou", {"StockID": code, **kw})
    return {"raw": data, "real": data.get("real") or {}, "weituo": data.get("weituo") or {},
            "ok": kpl.is_ok(data), "errcode": kpl.errcode(data)}


def bid(code: str, **kw) -> dict:
    """竞价分时：bid[[时间,价格,方向,量]] + preclose_px/hprice/lprice。"""
    data = kpl.call("stock_bid", {"StockID": code, **kw})
    return {"raw": data, "bid": _rows(data), "preclose": _num(data.get("preclose_px")),
            "high": _num(data.get("hprice")), "low": _num(data.get("lprice")), "ok": kpl.is_ok(data)}


def trend(code: str, **kw) -> dict:
    """分时：trend[[时间,价,均价,量,方向]]。"""
    data = kpl.call("stock_trend", {"StockID": code, **kw})
    return {"raw": data, "trend": _rows(data), "preclose": _num(data.get("preclose_px")),
            "ok": kpl.is_ok(data)}


def monitor(code: str, *, money: int | str = 2, is_bs: int | str = 0, st: int = 20, **kw) -> dict:
    """大单成交。money: 0=30万 1=50万 2=100万 3=300万 4=1000万；is_bs: 0全 1买 2卖。"""
    data = kpl.call("main_monitor", {"StockID": code, "Money": str(money), "IsBS": str(is_bs), "st": str(st), **kw})
    rows = _rows(data)
    items = []
    for r in rows:
        d = int(_num(_pick(r, 0, "bs", "方向", "BS")))
        items.append({
            "side": d,
            "side_text": {1: "被动卖", 2: "主动买", 3: "被动买", 4: "主动卖"}.get(d, str(d)),
            "ts": _pick(r, 1, "time", "ts", "时间"),
            "volume": _num(_pick(r, 2, "vol", "成交量")),
            "amount": _num(_pick(r, 3, "amount", "金额")),
            "avg_price": _num(_pick(r, 4, "avg", "均价")),
            "time": str(_pick(r, 5, "t", "时间2")),
        })
    # 方向编码：1 被动卖 / 2 主动买 / 3 被动买 / 4 主动卖 → 净额取主动买 - 主动卖
    active_buy = sum(x["amount"] for x in items if x["side"] == 2)
    active_sell = sum(x["amount"] for x in items if x["side"] == 4)
    return {"raw": data, "items": items, "count": len(items), "ok": kpl.is_ok(data),
            "active_buy": active_buy, "active_sell": active_sell, "net": active_buy - active_sell}


def weituo(code: str, *, vol: int | str = 500, tur: int | str = 30, vtype: int | str = 1, st: int = 3000, **kw) -> dict:
    """大单委托。vol 手数：500/1000/2000/5000/10000；tur 金额万：30/50/100/200/500/1000；vtype 1撤单 0未撤。"""
    data = kpl.call("weituo", {"StockID": code, "Vol": str(vol), "Tur": str(tur), "VType": str(vtype),
                               "st": str(st), **kw})
    rows = _rows(data)
    items = []
    for r in rows:
        items.append({
            "time": str(_pick(r, 0, "time", "时间")).zfill(6),
            "seq": _pick(r, 1, "id", "序号"),
            "price": _num(_pick(r, 2, "price", "价格")),
            "volume": _num(_pick(r, 3, "vol", "手数")),
            "amount": _num(_pick(r, 4, "amount", "成交额")),
            "side": _num(_pick(r, 5, "bs", "方向")),
            "canceled": _num(_pick(r, 6, "cancel", "撤单")),
        })
    buy = sum(x["amount"] for x in items if x["side"] in (1, 3, 5))
    sell = sum(x["amount"] for x in items if x["side"] in (2, 4, 6))
    return {"raw": data, "items": items, "count": len(items), "ok": kpl.is_ok(data),
            "buy": buy, "sell": sell, "net": buy - sell}


def chouma(code: str, day: str | None = None, **kw) -> dict:
    """筹码：day 为空走实时，否则走历史（Day 必须 YYYYMMDD）。"""
    if day:
        data = kpl.call("chouma_time_history", {"StockID": code, "Day": day, **kw})
    else:
        data = kpl.call("chouma_time_realtime", {"StockID": code, **kw})
    return {"raw": data, "rows": _rows(data), "ok": kpl.is_ok(data), "errcode": kpl.errcode(data)}


def dadan_trend(code: str, *, time: str = "15:00", **kw) -> dict:
    data = kpl.call("dadan_trend", {"StockID": code, "Time": time, **kw})
    return {"raw": data, "rows": _rows(data), "ok": kpl.is_ok(data)}


def pack(code: str, parts: tuple[str, ...] = ("pankou", "bid", "monitor", "weituo"), **kw) -> dict:
    """一次取多件套；单件失败不影响其它（errors 记录原因）。"""
    out: dict = {"code": str(code).zfill(6), "errors": {}}
    for p in parts:
        fn = {"pankou": pankou, "bid": bid, "trend": trend, "monitor": monitor,
              "weituo": weituo, "chouma": chouma, "dadan": dadan_trend}.get(p)
        if not fn:
            out["errors"][p] = "未知部件"
            continue
        try:
            out[p] = fn(code, **kw)
        except Exception as e:  # noqa: BLE001
            out["errors"][p] = str(e)
    out["summary"] = summary(out)
    return out


def summary(pack_data: dict) -> dict:
    """把 L2 件套压成可比较的标量（委比、大单净额、竞价强弱等）。"""
    s: dict = {}
    pk = pack_data.get("pankou") or {}
    if pk.get("weituo"):
        w = pk["weituo"]
        b = sum(_num(w.get("b%d" % i)) for i in range(1, 11))
        a = sum(_num(w.get("s%d" % i)) for i in range(1, 11))
        if b + a:
            s["weibi"] = round((b - a) / (b + a) * 100, 2)      # 五档委比 %
            s["bid_vol"] = b
            s["ask_vol"] = a
    real = pk.get("real") or {}
    if real:
        s["price"] = _num(real.get("px") or real.get("price") or real.get("now"))
        s["pct_chg"] = _num(real.get("zf") or real.get("pct") or real.get("zdf"))
    if pack_data.get("monitor"):
        m = pack_data["monitor"]
        s["big_net"] = m.get("net")
        s["big_buy"] = m.get("active_buy")
        s["big_sell"] = m.get("active_sell")
    if pack_data.get("weituo"):
        w = pack_data["weituo"]
        s["wt_net"] = w.get("net")
        s["wt_count"] = w.get("count")
    if pack_data.get("bid"):
        b = pack_data["bid"]
        last = b["bid"][-1] if b.get("bid") else None
        pre = b.get("preclose") or 0
        if last is not None and pre:
            s["auction_price"] = _num(_pick(last, 1, "price", "价格"))
            s["auction_pct"] = round((s["auction_price"] / pre - 1) * 100, 2) if pre else 0.0
    return s


def batch_monitor(codes: list[str], **kw) -> dict:
    """批量大单净额（供策略扫描用），带 1 层本地缓存。"""
    out = {}
    for c in codes:
        key = "l2:monitor:%s:%s" % (c, kw.get("money", 2))
        try:
            out[str(c).zfill(6)] = http.cached(key, 20, lambda c=c: monitor(c, **kw)["net"])
        except Exception as e:  # noqa: BLE001
            out[str(c).zfill(6)] = {"error": str(e)}
    return out
