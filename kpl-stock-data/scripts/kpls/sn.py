# -*- coding: utf-8 -*-
"""kpls.sn — 新浪财经（实时快照 / 批量 / 历史K线 / 沪深A股列表）。

实时：https://hq.sinajs.cn/list=sh600519,sz000001  （必须带 Referer，返回 GBK）
K线 ：https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
列表：vip.stock.finance.sina.com.cn Market_Center.getHQNodeData
"""
from __future__ import annotations

import re

from . import config, http

QUOTE_URL = "https://hq.sinajs.cn/list=%s"
KLINE_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             "CN_MarketData.getKLineData?symbol=%s&scale=%s&ma=no&datalen=%s")
LIST_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData?page=%s&num=%s&sort=symbol&asc=1&node=%s&symbol=&_s_r_a=page")
TIMEOUT = 15.0
UA = config.BROWSER_UA


def symbol(sym: str) -> str:
    """600519 / sh600519 / 1.600519 → sh600519。"""
    s = str(sym).strip().lower()
    if "." in s:
        mkt, code = s.split(".", 1)
        return ("sh" if mkt in ("1", "sh") else "sz") + code.zfill(6)
    if s.startswith(("sh", "sz", "bj")):
        return s
    s = s.zfill(6)
    if s.startswith(("600", "601", "603", "605", "688", "689", "900", "5", "1")):
        return "sh" + s
    return "sz" + s


def _headers() -> dict[str, str]:
    return {"Referer": "https://finance.sina.com.cn", "User-Agent": UA}


def quote(symbols: str | list[str]) -> list[dict]:
    """实时快照（未开盘返回 0 值；字段名对齐开盘啦/东财习惯）。"""
    syms = [symbol(s) for s in ([symbols] if isinstance(symbols, str) else list(symbols))]
    out: list[dict] = []
    for i in range(0, len(syms), 400):
        chunk = syms[i:i + 400]
        text = http.request(QUOTE_URL % ",".join(chunk), headers=_headers(), timeout=TIMEOUT,
                            encodings=("gbk", "gb18030"))
        for line in text.splitlines():
            m = re.match(r'var hq_str_(\w+)="(.*)";?', line.strip())
            if not m:
                continue
            sym, payload = m.group(1), m.group(2)
            f = payload.split(",")
            if len(f) < 32 or not any(f[1:6]):
                out.append({"symbol": sym, "code": sym[2:], "empty": True, "raw": payload})
                continue
            def num(idx: int) -> float:
                try:
                    return float(f[idx])
                except (ValueError, IndexError):
                    return 0.0

            pre = num(2)
            price = num(3) or pre
            out.append({
                "symbol": sym,
                "code": sym[2:],
                "name": f[0],
                "price": price,
                "open": num(1),
                "preclose": pre,
                "high": num(4),
                "low": num(5),
                "pct_chg": round((price / pre - 1) * 100, 3) if pre else 0.0,
                "change": round(price - pre, 3) if pre else 0.0,
                "volume": num(8),          # 股
                "amount": num(9),          # 元
                "bid1": num(11), "bid1_vol": num(10), "ask1": num(21), "ask1_vol": num(20),
                "date": f[30] if len(f) > 30 else "",
                "time": f[31] if len(f) > 31 else "",
                "source": "sina",
            })
    return out


def kline(sym: str, scale: int | str = 240, datalen: int = 240) -> list[dict]:
    """scale: 240日 / 1200周 / 7200月 / 5,15,30,60 分钟。不复权。"""
    text = http.request(KLINE_URL % (symbol(sym), scale, datalen), headers=_headers(),
                        timeout=TIMEOUT, encodings=("utf-8", "gbk"))
    data = http.load_json(text, KLINE_URL)
    out = []
    for r in data or []:
        try:
            out.append({
                "date": str(r.get("day")),
                "open": float(r.get("open")),
                "high": float(r.get("high")),
                "low": float(r.get("low")),
                "close": float(r.get("close")),
                "volume": float(r.get("volume")),  # 手
            })
        except (TypeError, ValueError):
            continue
    return out


def bars(sym: str, n: int = 120) -> list[dict]:
    """n 根日线（升序），字段与 ts.bars 对齐。"""
    rows = kline(sym, 240, max(int(n), 1) + 5)[-n:]
    for i, r in enumerate(rows):
        prev = rows[i - 1]["close"] if i else r["open"]
        r["pct_chg"] = round((r["close"] / prev - 1) * 100, 3) if prev else 0.0
    return rows


def codes(node: str = "hs_a", limit: int | None = None) -> list[str]:
    """沪深A股代码表（node: hs_a / sh_a / sz_a）。"""
    out: list[str] = []
    page = 1
    while True:
        text = http.request(LIST_URL % (page, 80, node), headers=_headers(), timeout=TIMEOUT,
                            encodings=("utf-8", "gbk"))
        data = http.load_json(text, LIST_URL)
        if not data:
            break
        for r in data:
            sym = str(r.get("symbol") or "")
            if sym:
                out.append(sym)
        if limit and len(out) >= limit:
            return out[:limit]
        if len(data) < 80:
            break
        page += 1
    return out


RANK_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData?page=%s&num=%s&sort=%s&asc=%s&node=%s&symbol=&_s_r_a=page")


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_a_share(code: str) -> bool:
    """过滤北交所（4/8/920 开头）与异常代码：保留沪 60/68、深 00/30/20。"""
    return len(code) == 6 and code.isdigit() and code.startswith(("60", "68", "00", "30", "20"))


def rank(node: str = "hs_a", *, sort: str = "amount", asc: bool = False, page: int = 1,
         num: int = 80) -> list[dict]:
    """新浪排行（EM push2 不可达时的候选池兜底）。

    sort: amount / volume / changepercent / turnoverratio / mktcap / nmc / per / pb。
    字段名与 em.clist 对齐（main_net 为 None，新浪无主力净额）。
    """
    fetch = min(max(int(num) * 3, int(num) + 40), 100)
    url = RANK_URL % (page, fetch, sort, 1 if asc else 0, node)
    text = http.request(url, headers=_headers(), timeout=TIMEOUT, encodings=("utf-8", "gbk"))
    data = http.load_json(text, url) or []
    out: list[dict] = []
    for r in data:
        code = str(r.get("code") or "").zfill(6)
        if not _is_a_share(code):
            continue
        out.append({
            "code": code,
            "name": r.get("name"),
            "price": _f(r.get("trade")),
            "pct_chg": _f(r.get("changepercent")),
            "change": _f(r.get("pricechange")),
            "open": _f(r.get("open")),
            "high": _f(r.get("high")),
            "low": _f(r.get("low")),
            "preclose": _f(r.get("settlement")),
            "volume": _f(r.get("volume")),
            "amount": _f(r.get("amount")),
            "turnover": _f(r.get("turnoverratio")),
            "vol_ratio": None,
            "main_net": None,
            "main_pct": None,
            "circ_mv": _f(r.get("nmc")),
            "total_mv": _f(r.get("mktcap")),
            "industry": None,
            "listing_date": None,
            "source": "sina-rank",
        })
    return out[:int(num)]