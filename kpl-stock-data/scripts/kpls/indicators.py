# -*- coding: utf-8 -*-
"""kpls.indicators — 本地指标计算（纯 Python，无 numpy/pandas 依赖）。

输入统一为 bars: list[dict]，升序，字段 date/open/close/high/low/volume(手)。
输出 compute() 一个大字典，可直接喂策略/选股。
"""
from __future__ import annotations

import math
from statistics import fmean


# ---------------------------------------------------------------- 基础
def closes(bars: list[dict]) -> list[float]:
    return [float(b.get("close") or 0) for b in bars]


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(round(sum(values[i + 1 - n:i + 1]) / n, 4))
    return out


def ema(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(round(out[-1] + k * (v - out[-1]), 4))
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    if len(values) < slow:
        return {"dif": None, "dea": None, "macd": None}
    ef, es = ema(values, fast), ema(values, slow)
    dif = [round(a - b, 4) for a, b in zip(ef, es)]
    dea = ema(dif, signal)
    return {"dif": dif[-1], "dea": dea[-1], "macd": round((dif[-1] - dea[-1]) * 2, 4),
            "golden": dif[-1] > dea[-1] and len(dif) > 1 and dif[-2] <= dea[-2],
            "dead": dif[-1] < dea[-1] and len(dif) > 1 and dif[-2] >= dea[-2]}


def rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) <= n:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(values) - n, len(values)):
        ch = values[i] - values[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return round(100 - 100 / (1 + rs), 2)


def kdj(bars: list[dict], n: int = 9) -> dict:
    if len(bars) < n:
        return {"k": None, "d": None, "j": None}
    k, d = 50.0, 50.0
    for i in range(n - 1, len(bars)):
        win = bars[i + 1 - n:i + 1]
        hi = max(float(b.get("high") or 0) for b in win)
        lo = min(float(b.get("low") or 0) for b in win)
        c = float(bars[i].get("close") or 0)
        rsv = 50.0 if hi == lo else (c - lo) / (hi - lo) * 100
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
    return {"k": round(k, 2), "d": round(d, 2), "j": round(3 * k - 2 * d, 2)}


def boll(values: list[float], n: int = 20, k: float = 2.0) -> dict:
    if len(values) < n:
        return {"up": None, "mid": None, "low": None, "pos": None}
    win = values[-n:]
    mid = fmean(win)
    sd = math.sqrt(sum((v - mid) ** 2 for v in win) / n)
    up, low = mid + k * sd, mid - k * sd
    cur = values[-1]
    return {"up": round(up, 3), "mid": round(mid, 3), "low": round(low, 3),
            "pos": round((cur - low) / (up - low) * 100, 2) if up > low else None}


def atr(bars: list[dict], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        h, l = float(bars[i].get("high") or 0), float(bars[i].get("low") or 0)
        pc = float(bars[i - 1].get("close") or 0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return round(fmean(trs), 3)


# ---------------------------------------------------------------- 涨跌停
def limit_pct(code: str, name: str = "") -> float:
    """涨停幅度：主板 10%、创业板/科创板 20%、北交所 30%、ST 5%。"""
    c = str(code).zfill(6)
    if "ST" in str(name).upper():
        return 5.0
    if c.startswith(("300", "301", "688", "689")):
        return 20.0
    if c.startswith(("4", "8")):
        return 30.0
    return 10.0


def is_limit_up(close: float, preclose: float, code: str, name: str = "") -> bool:
    if not preclose:
        return False
    return close >= round(preclose * (1 + limit_pct(code, name) / 100), 2) - 1e-6


def limit_stats(bars: list[dict], code: str, name: str = "", lookback: int = 60) -> dict:
    """近 lookback 日涨停统计 + 连板数（自最近往回数连续涨停）。"""
    win = bars[-lookback:]
    ups = 0
    for i in range(1, len(win)):
        if is_limit_up(float(win[i]["close"]), float(win[i - 1]["close"]), code, name):
            ups += 1
    streak = 0
    for i in range(len(win) - 1, 0, -1):
        if is_limit_up(float(win[i]["close"]), float(win[i - 1]["close"]), code, name):
            streak += 1
        else:
            break
    last_zt_days = None
    for i in range(len(win) - 1, 0, -1):
        if is_limit_up(float(win[i]["close"]), float(win[i - 1]["close"]), code, name):
            last_zt_days = len(win) - 1 - i
            break
    return {"zt_count": ups, "lianban": streak, "last_zt_days": last_zt_days}


# ---------------------------------------------------------------- 形态与量价
def vol_ratio(bars: list[dict], n: int = 5, elapsed_ratio: float = 1.0) -> float | None:
    """量比 = 当日量 / 前 n 日均量（alive 盘中传 elapsed_ratio<1 做等比例折算）。"""
    if len(bars) < n + 1:
        return None
    prev = [float(b.get("volume") or 0) for b in bars[-n - 1:-1]]
    avg = fmean(prev)
    if not avg:
        return None
    return round(float(bars[-1].get("volume") or 0) / avg / max(elapsed_ratio, 1e-6), 3)


def ma_multi(values: list[float]) -> dict:
    """均线多头排列（5>10>20>60）。"""
    if len(values) < 60:
        return {"bull": None, "above_ma5": None, "above_ma10": None, "above_ma20": None}
    m5, m10 = fmean(values[-5:]), fmean(values[-10:])
    m20, m60 = fmean(values[-20:]), fmean(values[-60:])
    cur = values[-1]
    return {"ma5": round(m5, 3), "ma10": round(m10, 3), "ma20": round(m20, 3), "ma60": round(m60, 3),
            "bull": m5 > m10 > m20 > m60, "above_ma5": cur > m5, "above_ma10": cur > m10,
            "above_ma20": cur > m20, "dist_ma5": round((cur / m5 - 1) * 100, 2) if m5 else None}


def position(bars: list[dict], n: int = 20) -> dict:
    win = bars[-n:]
    if not win:
        return {}
    hi = max(float(b.get("high") or 0) for b in win)
    lo = min(float(b.get("low") or 0) for b in win)
    cur = float(win[-1].get("close") or 0)
    return {"high": hi, "low": lo,
            "pos_pct": round((cur - lo) / (hi - lo) * 100, 2) if hi > lo else None}


def breakout(bars: list[dict], n: int = 20, tol: float = 0.005) -> dict:
    """平台突破：收盘创 n 日新高且量能放大。"""
    if len(bars) < n + 2:
        return {"ok": False}
    prev_hi = max(float(b.get("high") or 0) for b in bars[-n - 1:-1])
    cur = float(bars[-1].get("close") or 0)
    v_ratio = vol_ratio(bars, 5)
    return {"ok": cur >= prev_hi * (1 - tol), "prev_high": prev_hi, "close": cur,
            "vol_ratio": v_ratio, "strong": cur >= prev_hi * (1 - tol) and (v_ratio or 0) >= 1.2}


def pullback(bars: list[dict], ma: int = 5, tol: float = 0.01) -> dict:
    """回踩均线低吸：触及 ma 且未破、且前有涨停基因。"""
    vals = closes(bars)
    m = fmean(vals[-ma:]) if len(vals) >= ma else None
    if not m:
        return {"ok": False}
    cur = vals[-1]
    return {"ok": abs(cur / m - 1) <= tol, "ma%s" % ma: round(m, 3), "dist_pct": round((cur / m - 1) * 100, 2)}


def divergence(bars: list[dict], n: int = 20) -> dict:
    """量价背离提示：价新高量不配合 / 价新低量放大。"""
    if len(bars) < n:
        return {}
    win = bars[-n:]
    price_hi = max(float(b.get("close") or 0) for b in win) == float(win[-1].get("close") or 0)
    vol_hi = max(float(b.get("volume") or 0) for b in win) == float(win[-1].get("volume") or 0)
    return {"price_new_high_no_vol": bool(price_hi and not vol_hi),
            "price_new_high_with_vol": bool(price_hi and vol_hi)}


# ---------------------------------------------------------------- 综合
def compute(bars: list[dict], *, code: str = "", name: str = "", extra: dict | None = None) -> dict:
    """一个标的的全量本地指标。bars 需升序且 ≥ 2 根。"""
    if not bars or len(bars) < 2:
        return {"ok": False, "error": "bars 不足", "code": code}
    vals = closes(bars)
    last, prev = vals[-1], vals[-2]
    m = ma_multi(vals)
    out = {
        "ok": True,
        "code": str(code).zfill(6) if code else "",
        "name": name,
        "date": bars[-1].get("date"),
        "close": last,
        "pct_chg": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "volume": float(bars[-1].get("volume") or 0),
        "ma": m,
        "macd": macd(vals),
        "kdj": kdj(bars),
        "rsi14": rsi(vals, 14),
        "boll": boll(vals, 20),
        "atr14": atr(bars, 14),
        "vol_ratio5": vol_ratio(bars, 5),
        "pos20": position(bars, 20),
        "breakout20": breakout(bars, 20),
        "pullback_ma5": pullback(bars, 5),
        "divergence": divergence(bars, 20),
        "amount": float(bars[-1].get("amount") or 0),
    }
    if code:
        out["limit"] = limit_stats(bars, code, name)
    if extra:
        out.update(extra)
    out["score"] = score(out)
    out["signals"] = signals(out)
    return out


def score(ind: dict) -> int:
    """0-100 的粗打分：趋势 + 量能 + 位置 + 涨停基因（仅用于排序参考）。"""
    s = 50.0
    m = ind.get("ma") or {}
    if m.get("bull"):
        s += 12
    if m.get("above_ma5"):
        s += 5
    if m.get("above_ma20"):
        s += 5
    md = ind.get("macd") or {}
    if md.get("dif") is not None and md.get("dea") is not None and md["dif"] > md["dea"]:
        s += 6
    k = ind.get("kdj") or {}
    if k.get("k") is not None and k["k"] > 80:
        s -= 4
    vr = ind.get("vol_ratio5")
    if vr:
        s += min(max((vr - 1) * 8, -8), 10)
    p = (ind.get("pos20") or {}).get("pos_pct")
    if p is not None:
        s += (p - 50) / 10
    lim = ind.get("limit") or {}
    s += min((lim.get("zt_count") or 0) * 1.5, 12)
    if lim.get("lianban"):
        s += min(lim["lianban"] * 2, 8)
    if ind.get("breakout20", {}).get("strong"):
        s += 6
    r = ind.get("rsi14")
    if r and r > 85:
        s -= 6
    return int(max(0, min(100, round(s))))


def signals(ind: dict) -> list[str]:
    out = []
    m = ind.get("ma") or {}
    if m.get("bull"):
        out.append("均线多头")
    if ind.get("breakout20", {}).get("ok"):
        out.append("平台突破" + ("(放量)" if ind["breakout20"].get("strong") else ""))
    if ind.get("pullback_ma5", {}).get("ok"):
        out.append("回踩MA5")
    lim = ind.get("limit") or {}
    if lim.get("lianban"):
        out.append("%d连板" % lim["lianban"])
    elif lim.get("last_zt_days") == 0:
        out.append("首板")
    if (ind.get("vol_ratio5") or 0) >= 1.5:
        out.append("明显放量")
    if (ind.get("vol_ratio5") or 1) < 0.7:
        out.append("缩量")
    md = ind.get("macd") or {}
    if md.get("golden"):
        out.append("MACD金叉")
    if md.get("dead"):
        out.append("MACD死叉")
    if ind.get("divergence", {}).get("price_new_high_no_vol"):
        out.append("价涨量缩(背离)")
    return out


def chips_concentration(cyq_rows: list[dict]) -> dict:
    """筹码集中度：来自 tushare cyq_chips（price/percent）。"""
    if not cyq_rows:
        return {}
    rows = sorted(((float(r.get("price") or 0), float(r.get("percent") or 0)) for r in cyq_rows))
    total = sum(p for _, p in rows) or 1.0
    acc = 0.0
    p5 = p95 = rows[0][0]
    for price, pct in rows:
        acc += pct
        if p5 == rows[0][0] and acc >= total * 0.05:
            p5 = price
        if acc >= total * 0.95:
            p95 = price
            break
    return {"cost_5": round(p5, 3), "cost_95": round(p95, 3),
            "concentration": round((p95 - p5) / (p95 + p5) * 100, 2) if (p95 + p5) else None}


CATALOG = {
    "sma/ema": "均线（MA5/10/20/60）",
    "macd": "MACD(12,26,9) 含金叉/死叉",
    "kdj": "KDJ(9,3,3)",
    "rsi14": "RSI(14)",
    "boll": "BOLL(20,2) 含通道位置",
    "atr14": "ATR(14) 波动率",
    "vol_ratio5": "量比（对前 5 日均量）",
    "pos20": "20 日区间位置",
    "breakout20": "20 日平台突破 + 放量确认",
    "pullback_ma5": "回踩 MA5",
    "limit": "涨停基因：近 60 日涨停次数 / 连板数 / 距上次涨停",
    "divergence": "量价背离",
    "chips_concentration": "筹码集中度（tushare cyq_chips）",
    "score": "综合打分 0-100（趋势+量能+位置+涨停基因）",
    "signals": "信号标签列表",
}