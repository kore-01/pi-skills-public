# -*- coding: utf-8 -*-
"""kpls.em — 东方财富（延时/实时快照、批量、K线、排行榜、资金流、涨停池）。

端点：
  push2.eastmoney.com       实时（未授权也可用，偶有限流）
  push2delay.eastmoney.com  延时（目录默认，稳定）
  push2his.eastmoney.com    历史 K 线 / 资金流
  push2ex.eastmoney.com     涨停池 / 炸板池 / 跌停池
"""
from __future__ import annotations

import os
import time

from . import config, http

TIMEOUT = 18.0
UA = config.BROWSER_UA
_HOSTS = {"push2": "https://push2.eastmoney.com", "push2delay": "https://push2delay.eastmoney.com",
          "push2his": "https://push2his.eastmoney.com", "push2ex": "https://push2ex.eastmoney.com"}

FIELDS_QUOTE = "f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f168,f169,f170,f171,f116,f117,f162,f167,f127,f128"
FIELDS_LIST = "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f22,f23,f24,f25,f62,f115,f184,f100,f103"
FS_ALL_A = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

class Unavailable(RuntimeError):
    """东财行情节点（push2/push2his/push2delay）不可达。部分网络会整段拒绝这些 CDN 域，
    此时应改用新浪源（sn.bars / sn.quote / sn.rank）；push2ex（涨停池）通常仍然可用。"""


_BREAK: dict[str, dict] = {}
BREAK_THRESHOLD = 2
BREAK_SECONDS = 180.0


def _state(host: str) -> dict:
    return _BREAK.setdefault(host, {"fails": 0, "until": 0.0, "reason": ""})


def available(host: str = "push2delay") -> bool:
    if os.environ.get("KPLS_EM_FORCE"):
        return True
    return time.time() >= _state(host)["until"]


def _note_fail(host: str, err) -> None:
    st = _state(host)
    st["fails"] += 1
    st["reason"] = str(err)[:200]
    if st["fails"] >= BREAK_THRESHOLD:
        st["until"] = time.time() + BREAK_SECONDS


def _note_ok(host: str) -> None:
    st = _state(host)
    st["fails"] = 0
    st["until"] = 0.0
    st["reason"] = ""


def status() -> dict:
    """各节点可用性（供 doctor 诊断）。"""
    return {h: {"available": available(h), **_state(h)} for h in _HOSTS}

def _num(d: dict, key: str, div: float = 1.0):
    v = d.get(key)
    if v in (None, "-", ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f / div, 4) if div != 1 else f


def secid(sym: str, market: str | None = None) -> str:
    """600519 → 1.600519；000001 → 0.000001；sh000001 → 1.000001（指数亦适用）。"""
    s = str(sym).strip().lower()
    if "." in s and s.split(".")[0] in ("0", "1"):
        return s
    if s.startswith(("sh", "sz", "bj")):
        mkt = {"sh": "1", "sz": "0", "bj": "0"}[s[:2]]
        return "%s.%s" % (mkt, s[2:].zfill(6))
    s = s.zfill(6)
    if market in ("0", "1"):
        return "%s.%s" % (market, s)
    if s.startswith(("600", "601", "603", "605", "688", "689", "900")) or s.startswith(("5", "1")):
        return "1." + s
    return "0." + s


def _get(url: str, params: dict | None = None, *, host: str = "push2delay", timeout: float = TIMEOUT) -> dict:
    if not available(host):
        raise Unavailable("东财 %s 节点熔断中（%s）" % (host, _state(host)["reason"]))
    full = http.qs(_HOSTS[host] + url, params)
    try:
        data = http.get_json(full, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
                             timeout=timeout, encodings=("utf-8",), retries=0)
    except (http.NetError, http.HttpError) as e:
        _note_fail(host, e)
        raise Unavailable("东财 %s 不可达: %s" % (host, str(e)[:160])) from e
    _note_ok(host)
    return data if isinstance(data, dict) else {"data": data}


def quote(sym: str, *, fields: str = FIELDS_QUOTE, host: str = "push2delay") -> dict:
    data = _get("/api/qt/stock/get", {"secid": secid(sym), "fields": fields, "invt": 2, "fltt": 2}, host=host)
    d = (data or {}).get("data") or {}
    if not d:
        return {"ok": False, "raw": data}
    return {"ok": True, "raw": d, "decoded": _decode_quote(d)}


def ulist(symbols: list[str] | str, *, fields: str = "f2,f3,f4,f12,f14,f62,f184,f8,f20,f21", host: str = "push2delay") -> list[dict]:
    syms = [symbols] if isinstance(symbols, str) else list(symbols)
    secids = ",".join(secid(s) for s in syms)
    data = _get("/api/qt/ulist.np/get", {"secids": secids, "fields": fields, "fltt": 2, "invt": 2}, host=host)
    diff = ((data or {}).get("data") or {}).get("diff") or []
    return [_decode_quote(r) for r in diff]


def _decode_quote(d: dict) -> dict:
    """东财字段解码。

    push2 行情族（f43/f44/f46/f60/f168.. 原始值为 ×100 整数）→ 除 100；
    clist/ulist 列表族（fltt=2，f2/f3/f8/f10/f184 已是人类单位）→ 不除。
    """
    push2 = any(k in d for k in ("f43", "f44", "f45", "f46", "f60", "f168", "f169", "f170", "f50"))
    div = 100 if push2 else 1
    return {
        "code": d.get("f12") or d.get("f57"),
        "name": d.get("f14") or d.get("f58"),
        "price": _num(d, "f43", div) if "f43" in d else _num(d, "f2", div),
        "pct_chg": _num(d, "f170", div) if "f170" in d else _num(d, "f3", div),
        "change": _num(d, "f169", div) if "f169" in d else _num(d, "f4", div),
        "open": _num(d, "f46", div) if "f46" in d else _num(d, "f17", div),
        "high": _num(d, "f44", div) if "f44" in d else _num(d, "f15", div),
        "low": _num(d, "f45", div) if "f45" in d else _num(d, "f16", div),
        "preclose": _num(d, "f60", div) if "f60" in d else _num(d, "f18", div),
        "volume": d.get("f47") or d.get("f5"),
        "amount": d.get("f48") or d.get("f6"),
        "turnover": _num(d, "f168", div) if "f168" in d else _num(d, "f8", div),
        "vol_ratio": _num(d, "f50", div) if "f50" in d else _num(d, "f10", div),
        "main_net": d.get("f62"),
        "main_pct": _num(d, "f184", div),
        "circ_mv": d.get("f21"),
        "total_mv": d.get("f20"),
        "industry": d.get("f100") or d.get("f127"),
        "listing_date": d.get("f189"),
        "source": "eastmoney",
    }


def kline(sym: str, *, klt: int = 101, fqt: int = 1, lmt: int = 240, beg: str | None = None,
          end: str | None = None) -> list[dict]:
    """klt: 1/5/15/30/60 分钟；101 日 102 周 103 月。fqt: 0 不复权 1 前复权 2 后复权。"""
    params = {"secid": secid(sym), "klt": klt, "fqt": fqt, "fields1": "f1,f2,f3,f4,f5,f6",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"}
    if beg:
        params["beg"] = beg
    if end:
        params["end"] = end
    if not beg:
        params["lmt"] = lmt
    data = _get("/api/qt/stock/kline/get", params, host="push2his")
    kl = ((data or {}).get("data") or {}).get("klines") or []
    out = []
    for row in kl:
        p = str(row).split(",")
        if len(p) < 8:
            continue
        try:
            out.append({
                "date": p[0],
                "open": float(p[1]), "close": float(p[2]), "high": float(p[3]), "low": float(p[4]),
                "volume": float(p[5]), "amount": float(p[6]),
                "amplitude": float(p[7]) if p[7] not in ("-", "") else 0.0,
                "pct_chg": float(p[8]) if len(p) > 8 and p[8] not in ("-", "") else 0.0,
                "change": float(p[9]) if len(p) > 9 and p[9] not in ("-", "") else 0.0,
                "turnover": float(p[10]) if len(p) > 10 and p[10] not in ("-", "") else 0.0,
            })
        except ValueError:
            continue
    return out


def bars(sym: str, n: int = 120, *, fqt: int = 1) -> list[dict]:
    return kline(sym, klt=101, fqt=fqt, lmt=max(int(n), 1))[-n:]


def clist(*, fs: str = FS_ALL_A, fields: str = FIELDS_LIST, fid: str = "f3", po: int = 1,
          pn: int = 1, pz: int = 50, host: str = "push2") -> list[dict]:
    """行情列表/排行（选股扫描主入口）：pz 每页条数，po=1 降序 0 升序。"""
    data = _get("/api/qt/clist/get", {"pn": pn, "pz": pz, "po": po, "fid": fid, "fs": fs,
                                      "fields": fields, "fltt": 2, "invt": 2, "np": 1}, host=host)
    diff = ((data or {}).get("data") or {}).get("diff") or []
    return [_decode_quote(r) for r in diff]


def fflow(sym: str, *, lmt: int = 0, klt: int = 0) -> dict:
    """个股资金流：klt=0 日线（默认 60 条），klt=1 分钟。返回 {series:[...], today:{...}}。"""
    params = {"secid": secid(sym), "lmt": lmt, "klt": klt,
              "fields1": "f1,f2,f3,f7",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"}
    data = _get("/api/qt/stock/fflow/kline/get", params, host="push2his")
    kl = ((data or {}).get("data") or {}).get("klines") or []
    series = []
    for row in kl:
        p = str(row).split(",")
        if len(p) < 6:
            continue
        series.append({
            "date": p[0],
            "main_net": float(p[1] or 0), "small_net": float(p[2] or 0), "mid_net": float(p[3] or 0),
            "large_net": float(p[4] or 0), "super_net": float(p[5] or 0),
        })
    today = series[-1] if series else {}
    return {"series": series, "today": today, "count": len(series), "source": "eastmoney"}


def zt_pool(date: str | None = None) -> list[dict]:
    """涨停池（getTopicZTPool）。date=YYYYMMDD。"""
    d = date or time.strftime("%Y%m%d")
    data = _get("/getTopicZTPool", {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                                    "Pageindex": 0, "pagesize": 300, "sort": "fbt:asc", "date": d},
                host="push2ex")
    rows = ((data or {}).get("data") or {}).get("pool") or []
    return [{
        "code": str(r.get("c")), "name": r.get("n"), "price": (r.get("p") or 0) / 1000,
        "pct_chg": r.get("zdp"), "amount": r.get("amount"), "turnover": r.get("hs"),
        "first_seal": str(r.get("fbt") or "").zfill(6), "last_seal": str(r.get("lbt") or "").zfill(6),
        "open_times": r.get("zbc"), "boards": r.get("lbc"), "plate": r.get("hybk"),
        "seal_amount": r.get("fund"), "circ_mv": r.get("tshare"), "source": "eastmoney",
    } for r in rows]


def break_pool(date: str | None = None) -> list[dict]:
    """炸板池（getTopicZBPool）。"""
    d = date or time.strftime("%Y%m%d")
    data = _get("/getTopicZBPool", {"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
                                    "Pageindex": 0, "pagesize": 300, "sort": "fbt:asc", "date": d},
                host="push2ex")
    rows = ((data or {}).get("data") or {}).get("pool") or []
    return [{
        "code": str(r.get("c")), "name": r.get("n"), "price": (r.get("p") or 0) / 1000,
        "pct_chg": r.get("zdp"), "first_seal": str(r.get("fbt") or "").zfill(6),
        "open_times": r.get("zbc"), "boards": r.get("lbc"), "plate": r.get("hybk"),
        "amount": r.get("amount"), "source": "eastmoney",
    } for r in rows]


def market_overview() -> dict:
    """大盘涨跌家数（上证/深证/创业板指数 + 涨跌统计）。"""
    idx = ulist(["sh000001", "sz399001", "sz399006"], fields="f2,f3,f4,f12,f14,f6", host="push2delay")
    return {"indices": idx, "source": "eastmoney", "at": time.strftime("%Y-%m-%d %H:%M:%S")}
