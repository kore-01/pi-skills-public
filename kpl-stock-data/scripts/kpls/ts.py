# -*- coding: utf-8 -*-
"""kpls.ts — Tushare Pro（https://api.tushare.pro，POST JSON，内置 token）。

返回统一为 list[dict]（字段名 → 值）。权限不足会抛 TushareError 并带原始 msg，
由调用方决定降级（例如 stk_auction_o 需单独权限 → 退回 em/sn）。
"""
from __future__ import annotations

import os
import sys
import time

from . import config, http

API_URL = os.environ.get("TUSHARE_API") or "https://api.tushare.pro"
TIMEOUT = 40.0


class TushareError(RuntimeError):
    def __init__(self, msg: str, code: int = -1, api_name: str = ""):
        self.code = code
        self.api_name = api_name
        super().__init__("tushare %s code=%s %s" % (api_name, code, msg))

_INSECURE = os.environ.get("TUSHARE_INSECURE") == "1"
_WARNED = False


def _post(body: dict, timeout: float) -> dict:
    """首次用系统证书；若证书链校验失败（本机缺中间证书/被代理）则自动降级为不校验。"""
    global _INSECURE, _WARNED
    try:
        return http.post_json(API_URL, body, timeout=timeout, retries=0, insecure=_INSECURE)
    except http.NetError as e:
        if _INSECURE or "CERTIFICATE" not in str(e).upper():
            raise
        _INSECURE = True
        if not _WARNED:
            _WARNED = True
            print("[kpls] api.tushare.pro 证书校验失败，已降级为不校验 TLS（仅本机自用）", file=sys.stderr)
        return http.post_json(API_URL, body, timeout=timeout, retries=0, insecure=True)
_SH_MARKETS = ("600", "601", "603", "605", "688", "689", "900", "5", "1")


def to_ts_code(symbol: str) -> str:
    """6 位代码 / 交易所前缀 → tushare ts_code（600519 → 600519.SH）。"""
    s = str(symbol).strip().upper()
    if "." in s and s.split(".")[-1] in ("SH", "SZ", "BJ"):
        return s
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "").lstrip(".")
    s = s.zfill(6)
    if s.startswith(("600", "601", "603", "605", "688", "689", "900", "5")):
        return s + ".SH"
    if s.startswith(("4", "8")):
        return s + ".BJ"
    return s + ".SZ"


def pro_raw(api_name: str, *, token: str | None = None, fields: str = "", timeout: float = TIMEOUT,
            retries: int = 1, **params) -> dict:
    tok = token or config.tushare_token()
    if not tok:
        raise TushareError("未找到 Tushare Token（env TUSHARE_TOKEN / assets/tushare.token）", -1, api_name)
    body = {"api_name": api_name, "token": tok, "params": params, "fields": fields}
    payload = {"code": 0, "msg": None, "data": None}
    for attempt in range(retries + 1):
        payload = _post(body, timeout)
        code = int((payload or {}).get("code") or 0)
        if code == 0:
            return payload
        msg = str((payload or {}).get("msg") or "")
        if attempt < retries and ("每分钟" in msg or "频率" in msg or "timeout" in msg.lower()):
            time.sleep(1.2 * (attempt + 1))
            continue
        raise TushareError(msg, code, api_name)
    return payload


def pro(api_name: str, *, fields: str = "", token: str | None = None, **params) -> list[dict]:
    """通用调用：返回 rows（list[dict]）。"""
    payload = pro_raw(api_name, token=token, fields=fields, **params)
    data = (payload or {}).get("data") or {}
    cols = list(data.get("fields") or [])
    items = data.get("items") or []
    if not cols:
        return []
    return [dict(zip(cols, row)) for row in items]


# ---------------------------------------------------------------- 常用封装
def daily(ts_code: str | None = None, *, symbol: str | None = None, trade_date: str | None = None,
          start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    p = dict(kw)
    if symbol and not ts_code:
        ts_code = to_ts_code(symbol)
    for k, v in (("ts_code", ts_code), ("trade_date", trade_date), ("start_date", start_date), ("end_date", end_date)):
        if v:
            p[k] = v
    return pro("daily", **p)


def adj_factor(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("adj_factor", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def daily_basic(ts_code: str | None = None, trade_date: str | None = None, **kw) -> list[dict]:
    p = {k: v for k, v in (("ts_code", ts_code and to_ts_code(ts_code)), ("trade_date", trade_date)) if v}
    p.update(kw)
    return pro("daily_basic", **p)


def stock_basic(**kw) -> list[dict]:
    kw.setdefault("list_status", "L")
    return pro("stock_basic", **kw)


def trade_cal(start_date: str | None = None, end_date: str | None = None, exchange: str = "SSE", **kw) -> list[dict]:
    return pro("trade_cal", exchange=exchange, start_date=start_date, end_date=end_date, **kw)


def index_daily(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("index_daily", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def limit_list_d(trade_date: str | None = None, *, limit_type: str | None = None, **kw) -> list[dict]:
    """涨跌停/炸板列表（limit_type=U涨停 D跌停 Z炸板）。"""
    p = {k: v for k, v in (("trade_date", trade_date), ("limit_type", limit_type)) if v}
    p.update(kw)
    return pro("limit_list_d", **p)


def moneyflow(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("moneyflow", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def hm_detail(trade_date: str | None = None, **kw) -> list[dict]:
    p = {k: v for k, v in (("trade_date", trade_date),) if v}
    p.update(kw)
    return pro("hm_detail", **p)


def top_inst(trade_date: str, **kw) -> list[dict]:
    return pro("top_inst", trade_date=trade_date, **kw)


def top_list(trade_date: str, **kw) -> list[dict]:
    return pro("top_list", trade_date=trade_date, **kw)


def stk_factor(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("stk_factor", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def stk_factor_pro(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("stk_factor_pro", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def cyq_perf(ts_code: str, start_date: str | None = None, end_date: str | None = None, **kw) -> list[dict]:
    return pro("cyq_perf", ts_code=to_ts_code(ts_code), start_date=start_date, end_date=end_date, **kw)


def cyq_chips(ts_code: str, trade_date: str | None = None, **kw) -> list[dict]:
    return pro("cyq_chips", ts_code=to_ts_code(ts_code), trade_date=trade_date, **kw)


def kpl_concept_cons(trade_date: str | None = None, **kw) -> list[dict]:
    p = {k: v for k, v in (("trade_date", trade_date),) if v}
    p.update(kw)
    return pro("kpl_concept_cons", **p)


def dc_concept(trade_date: str | None = None, **kw) -> list[dict]:
    p = {k: v for k, v in (("trade_date", trade_date),) if v}
    p.update(kw)
    return pro("dc_concept", **p)


def stk_auction_o(trade_date: str, **kw) -> list[dict]:
    return pro("stk_auction_o", trade_date=trade_date, **kw)


# ---------------------------------------------------------------- 组合工具
def recent_trade_days(n: int = 60, *, end: str | None = None) -> list[str]:
    end = end or time.strftime("%Y%m%d")
    start = time.strftime("%Y%m%d", time.localtime(time.time() - max(n, 10) * 4 * 86400))
    cal = trade_cal(start_date=start, end_date=end)
    days = sorted(str(r.get("cal_date")) for r in cal if str(r.get("is_open")) == "1")
    return days[-n:]


def last_trade_day(*, end: str | None = None) -> str:
    days = recent_trade_days(3, end=end)
    today = time.strftime("%Y%m%d")
    past = [d for d in days if d <= today]
    return past[-1] if past else (days[-1] if days else today)


def bars(symbol: str, n: int = 120, *, adj: bool = False, end: str | None = None) -> list[dict]:
    """取 n 根日线（升序），字段 date/open/close/high/low/volume/amount，可直接喂 indicators。"""
    ts_code = to_ts_code(symbol)
    end = end or last_trade_day()
    start = time.strftime("%Y%m%d", time.localtime(time.time() - n * 4 * 86400))
    rows = daily(ts_code, start_date=start, end_date=end)
    rows = sorted(rows, key=lambda r: str(r.get("trade_date")))
    rows = rows[-n:]
    if adj and rows:
        f = {str(r.get("trade_date")): r.get("adj_factor") for r in adj_factor(ts_code, start_date=start, end_date=end)}
        base = None
        for r in reversed(rows):
            v = f.get(str(r.get("trade_date")))
            if v:
                base = float(v)
                break
        if base:
            for r in rows:
                v = f.get(str(r.get("trade_date")))
                if v:
                    k = float(v) / base
                    for fld in ("open", "close", "high", "low"):
                        if r.get(fld) is not None:
                            r[fld] = round(float(r[fld]) * k, 3)
    out = []
    for r in rows:
        out.append({
            "date": str(r.get("trade_date")),
            "open": float(r.get("open") or 0),
            "close": float(r.get("close") or 0),
            "high": float(r.get("high") or 0),
            "low": float(r.get("low") or 0),
            "volume": float(r.get("vol") or 0),      # 手
            "amount": float(r.get("amount") or 0),   # 千元
            "pct_chg": float(r.get("pct_chg") or 0),
        })
    return out
