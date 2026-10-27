# -*- coding: utf-8 -*-
"""kpls.router — 统一入口：按接口 id 自动路由到对应数据源。

  kpl     → 开盘啦官方 longhuvip（内置 2 账号 failover）
  py590   → 平台 py.590.net / i.590.net（双机互备，需 Token）
  tushare → Tushare Pro（ts_* → api_name）
  sina    → 新浪（sn_*）
  eastmoney → 东方财富（em_*）
  other   → 直连 URL（选股宝涨停池 / 复盘网 / 文章接口等）
"""
from __future__ import annotations

from . import catalog, config, em, http, kpl, py590, sn, ts


def call(api_id: str, params: dict | None = None, **kw) -> object:
    api = catalog.find(api_id)
    src = catalog.source_of(api)
    p = dict(params or {})
    if src == "kpl":
        return kpl.call(api_id, p, **kw)
    if src == "py590":
        return py590.call(api_id, p, **kw)
    if src == "tushare":
        return _tushare(api, p)
    if src == "sina":
        return _sina(api, p)
    if src == "eastmoney":
        return _em(api, p)
    return _raw(api, p)


def _clean(p: dict) -> dict:
    return {k: v for k, v in p.items() if v is not None and str(v) != ""}


def _tushare(api: dict, p: dict) -> list[dict]:
    api_id = str(api.get("id"))
    name = api_id[3:] if api_id.startswith("ts_") else api_id
    fields = p.pop("fields", "")
    if "symbol" in p and "ts_code" not in p:
        p["ts_code"] = ts.to_ts_code(p.pop("symbol"))
    p.pop("symbol", None)
    return ts.pro(name, fields=fields, **_clean(p))


def _sina(api: dict, p: dict) -> object:
    api_id = str(api.get("id"))
    if api_id == "sn_quote":
        return sn.quote(p.get("symbol") or p.get("symbols") or p.get("code"))
    if api_id == "sn_ulist":
        return sn.quote(p.get("symbols") or p.get("symbol") or p.get("code"))
    if api_id == "sn_kline":
        scale = p.get("scale")
        if not scale:
            scale = {"day": 240, "week": 1200, "month": 7200}.get(str(p.get("period") or "").lower(), 240)
        datalen = p.get("datalen") or p.get("lmt") or p.get("bars") or 240
        return sn.kline(p.get("symbol") or p.get("code"), scale, int(datalen))
    if api_id == "sn_codes":
        return sn.codes(p.get("node") or "hs_a", int(p["limit"]) if p.get("limit") else None)
    return sn.quote(p.get("symbol") or p.get("code"))


def _em(api: dict, p: dict) -> object:
    api_id = str(api.get("id"))
    sym = p.get("symbol") or p.get("code")
    if api_id == "em_quote":
        return em.quote(sym, fields=p.get("fields") or em.FIELDS_QUOTE)
    if api_id == "em_ulist":
        return em.ulist(p.get("symbols") or sym, fields=p.get("fields") or "f2,f3,f4,f12,f14,f62,f184,f8")
    if api_id in ("em_kline", "em_kline_1m"):
        klt = 1 if api_id == "em_kline_1m" else int(p.get("klt") or 101)
        lmt = int(p.get("lmt") or p.get("datalen") or p.get("bars") or (120 if klt == 1 else 240))
        return em.kline(sym, klt=klt, fqt=int(p.get("fqt") or 1), lmt=lmt,
                        beg=p.get("beg"), end=p.get("end"))
    return em.quote(sym)


def _raw(api: dict, p: dict) -> object:
    """直连型接口：URL 里带 {占位符} 的用参数填充，其余原样请求。"""
    url = str(api.get("url") or "")
    for k, v in _clean(p).items():
        url = url.replace("{%s}" % k, str(v))
    if "{" in url:
        left = catalog.placeholders_in(url)
        raise ValueError("缺少参数: %s" % ", ".join(sorted(set(left))))
    method = str(api.get("method") or "GET").upper()
    headers = {"User-Agent": config.BROWSER_UA, "Referer": "https://www.kaipanla.com/"}
    return http.get_json(url, headers=headers) if method == "GET" else http.post_form(url, {}, headers=headers)
