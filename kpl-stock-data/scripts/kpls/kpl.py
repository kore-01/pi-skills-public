# -*- coding: utf-8 -*-
"""kpls.kpl — 开盘啦官方接口驱动（*.longhuvip.com），内置多账号自动 failover。

设计要点（对齐 kpl-cli/kpl_fetch/executor.py 的实测行为）：
  * 鉴权 = query string 里的 Token/UserID/DeviceID/VerSion/apiv/PhoneOSNew（不写代码里）
  * POST = 空 body + 全部参数在 URL query（longhuvip 的怪癖，末尾可带 &）
  * URL 模板占位符 {Token} {UserID} {DeviceID} {StockID} {PlateID} ... 逐个填充
  * 历史接口 Today/周末会返回 1020 → 默认回退上一交易日
  * 软错误码（1130 暂无数据 / 1001 非交易日 / 1002 无权限 / 1020 参数）→ 当空结果
  * 账号轮换：默认按持久化游标在 2 个全功能账号间**主动轮换**打头（`KPLS_ACCOUNT_ROTATE=0` 关闭）；
    遇到 998/1003/1004/1060/-1/-2（凭证失效/限流）自动切下一个内置账号
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from . import catalog, config, http

TZ = ZoneInfo("Asia/Shanghai")
TIMEOUT = 18.0

SOFT_ERRCODES = {"1130", "1001", "1002", "1020"}
ROTATE_ERRCODES = {"998", "1003", "1004", "1060", "-1", "-2"}

_STOCK_DEFAULT = "000001"
_PLATE_DEFAULT = "801003"

API_DEFAULTS: dict[str, dict[str, str]] = {
    "main_monitor": {"StockID": _STOCK_DEFAULT, "Money": "2", "IsBS": "0", "Index": "0", "st": "20"},
    "weituo": {"StockID": _STOCK_DEFAULT, "Vol": "500", "Tur": "30", "VType": "1", "Type": "2",
               "VOrder": "0", "st": "3000"},
    "kline_day": {"StockID": _STOCK_DEFAULT, "Type": "d", "Is_FS": "1", "Index": "0", "st": "120"},
    "stock_trend": {"StockID": _STOCK_DEFAULT, "Type": "1"},
    "stock_trend_history": {"StockID": _STOCK_DEFAULT},
    "pankou": {"StockID": _STOCK_DEFAULT},
    "stock_bid": {"StockID": _STOCK_DEFAULT},
    "chouma_time_realtime": {"StockID": _STOCK_DEFAULT},
    "chouma_time_history": {"StockID": _STOCK_DEFAULT},
    "dadan_trend": {"StockID": _STOCK_DEFAULT, "Time": "15:00"},
    "kline_zhangting_today": {"StockID": _STOCK_DEFAULT},
    "kline_zhangting_history": {"StockID": _STOCK_DEFAULT},
    "zhangting_gene": {"StockID": _STOCK_DEFAULT},
    "stock_plate": {"StockID": _STOCK_DEFAULT},
    "gudong_change": {"StockID": _STOCK_DEFAULT},
    "jg_tracking_stock": {"StockID": _STOCK_DEFAULT},
    "morning_bidding_realtime": {"Type": "4", "PidType": "0", "Order": "1", "Index": "0", "st": "60"},
    "morning_bidding_history": {"Type": "4", "PidType": "0", "Order": "1", "Index": "0", "st": "60"},
    "morning_bidding_top20": {"Type": "10", "PidType": "1", "Order": "1", "Index": "0", "st": "20"},
    "longhubang_buy_sell": {"Type": "0", "StockID": _STOCK_DEFAULT},
    "daily_limit_realtime": {"PidType": "1"},
    "daily_limit_history": {"PidType": "1"},
    "daily_limit2_realtime": {"PidType": "1"},
    "daily_limit2_history": {"PidType": "1"},
    "plate_stocks_main_net": {"PlateID": _PLATE_DEFAULT},
    "plate_stocks_change": {"PlateID": _PLATE_DEFAULT},
    "plate_limit_count": {"PlateID": _PLATE_DEFAULT},
    "plate_ranking_realtime": {"ZSType": "7", "Type": "1", "Index": "0"},
    "plate_ranking_history": {"ZSType": "7", "Type": "1", "Index": "0"},
    "damian": {},
    "ydtp_today": {},
    "bk_jj_stocks": {"StockID": _PLATE_DEFAULT},
    "jgcc_stocks": {"IndexID": _PLATE_DEFAULT},
    "bxzj_stocks": {"IndexID": _PLATE_DEFAULT},
    "topic_get": {"ID": "2160"},
    "topic_zs": {"ZS": "801660", "ID": "2160"},
    "题材库": {"ID": "25"},
    "disk_review": {},
    "market_capacity": {"Type": "0"},
    "zhangting_expression": {},
    "interview_zs": {},
    "interview_stock": {"StockID": _STOCK_DEFAULT},
}


# ---------------------------------------------------------------- 交易日辅助
def now_sh() -> datetime:
    return datetime.now(TZ)


def today_str() -> str:
    return now_sh().strftime("%Y-%m-%d")


def last_trade_day(today: date | None = None) -> str:
    """最近交易日（跳过周末，不含节假日表）。"""
    d = today or now_sh().date()
    for _ in range(10):
        if d.weekday() < 5:
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def prev_trade_day(today: date | None = None) -> str:
    """上一已结束交易日（从昨天往回跳过周末）——历史接口默认值。"""
    d = (today or now_sh().date()) - timedelta(days=1)
    for _ in range(15):
        if d.weekday() < 5:
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 参数合并
def merge_params(api_id: str, user: dict | None = None, ph: dict[str, str] | None = None) -> dict[str, str]:
    merged: dict[str, str] = dict(ph or {})
    merged.update(API_DEFAULTS.get(api_id, {}))
    for k, v in (user or {}).items():
        if v is None or str(v).strip() == "":
            continue
        merged[str(k)] = str(v).strip()

    # 别名
    if "StockID" not in merged and "code" in merged:
        merged["StockID"] = str(merged["code"]).zfill(6)
    if "StockID" in merged:
        merged["StockID"] = str(merged["StockID"]).zfill(6)
    if "IndexID" not in merged and "PlateID" in merged:
        merged["IndexID"] = merged["PlateID"]
    if "IndexID" not in merged and "ZSCode" in merged:
        merged["IndexID"] = merged["ZSCode"]
    if "PlateID" not in merged and "IndexID" in merged:
        merged["PlateID"] = merged["IndexID"]

    hist_day = prev_trade_day()
    tod = today_str()

    def _is_today(val: str) -> bool:
        s = str(val or "").strip()[:10]
        return s in ("", tod) or s.replace("-", "") == tod.replace("-", "")

    # 精选板块历史：Type 固定 1；今天 → 上一交易日
    if api_id == "plate_ranking_history":
        if _is_today(merged.get("Date") or ""):
            merged["Date"] = merged["date"] = merged["Day"] = hist_day
        merged["ZSType"] = merged.get("ZSType") or "7"
        merged["Type"] = "1"
        merged.setdefault("Index", "0")
        merged.pop("RStart", None)
        merged.pop("REnd", None)

    # 竞价池历史：今天/周末 → 上一交易日；清实时脏参
    if api_id == "morning_bidding_history":
        bad = _is_today(merged.get("Date") or "")
        if not bad and len(str(merged.get("Date"))) >= 10:
            try:
                bad = date.fromisoformat(str(merged["Date"])[:10]).weekday() >= 5
            except ValueError:
                bad = True
        if bad:
            merged["Date"] = merged["date"] = merged["Day"] = hist_day
        merged["Type"] = "4"
        merged.setdefault("PidType", "0")
        merged.setdefault("Index", "0")
        for junk in ("ZSType", "RStart", "REnd", "StockID", "PlateID"):
            merged.pop(junk, None)

    if api_id == "morning_bidding_realtime":
        merged["Type"] = "4"
        if str(merged.get("PidType") or "") == "":
            merged["PidType"] = "0"
        for junk in ("Date", "Day", "date", "ZSType", "RStart", "REnd", "StockID", "PlateID"):
            merged.pop(junk, None)

    # 板块成分变动：REnd 必须 5 分钟对齐且 ≤ 1130（窗口上限上午收盘）
    if api_id == "plate_stocks_change":
        n = now_sh()
        m = (n.hour * 60 + n.minute) // 5 * 5
        m = min(max(m, 9 * 60 + 30), 11 * 60 + 30)
        merged["RStart"] = "0925"
        merged["REnd"] = "%02d%02d" % (m // 60, m % 60)

    if "DStart" not in merged or "DEnd" not in merged:
        end = date.fromisoformat(last_trade_day())
        start = end - timedelta(days=14)
        while start.weekday() >= 5:
            start += timedelta(days=1)
        merged.setdefault("DEnd", end.strftime("%Y-%m-%d"))
        merged.setdefault("DStart", start.strftime("%Y-%m-%d"))

    # 分时大单历史：Day 必须 YYYYMMDD
    if api_id == "chouma_time_history" and merged.get("Day"):
        merged["Day"] = str(merged["Day"]).replace("-", "")[:8]

    if api_id == "plate_ranking_realtime":
        merged.setdefault("ZSType", "7")
        merged.setdefault("Index", "0")
        if str(merged.get("Type") or "") in ("", "4"):
            merged["Type"] = "1"

    if api_id == "damian":
        if _is_today(merged.get("Date") or ""):
            merged["Date"] = hist_day
        for junk in ("Type", "ZSType", "RStart", "REnd", "StockID", "PidType"):
            merged.pop(junk, None)

    if api_id == "ydtp_today":
        for junk in ("Type", "Date", "Day", "ZSType", "RStart", "REnd", "StockID", "Index", "PidType", "PlateID"):
            merged.pop(junk, None)
        merged["apiv"] = "w34"
        merged["VerSion"] = "5.13.0.0"

    return merged


def _fill(text: str, params: dict[str, str]) -> str:
    for key, val in params.items():
        text = text.replace("{%s}" % key, str(val))
    return text


def build_request(api: dict, params: dict[str, str]) -> tuple[str, str, list[str]]:
    """返回 (url, method, 未填充的占位符列表)。"""
    url = _fill(str(api.get("url") or ""), params)
    method = str(api.get("method") or "POST").upper()
    parts = urlsplit(url)
    q = [(k, _fill(v, params)) for k, v in parse_qsl(parts.query, keep_blank_values=True)]

    # 官方域名需补全鉴权参数
    if "longhuvip" in parts.netloc:
        keys = {k for k, _ in q}
        for k, v in params.items():
            if k in ("Token", "UserID", "DeviceID", "VerSion", "apiv", "PhoneOSNew") and k not in keys:
                q.append((k, v))
        q = [(k, (params.get("UserID") or v) if (k == "UserID" and str(v) in ("0", "")) else v) for k, v in q]

    final = urlencode(q, doseq=True)
    leftovers = catalog.placeholders_in(urlunsplit(parts._replace(query=final)))
    if "longhuvip" in parts.netloc and final and method == "POST" and not final.endswith("&"):
        final += "&"
    return urlunsplit(parts._replace(query=final)), method, sorted(set(leftovers))


def redact(url: str) -> str:
    """日志用：隐藏 Token。"""
    parts = urlsplit(url)
    q = [(k, "***" if k == "Token" else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(q)))


def fetch(api: dict, params: dict[str, str]) -> tuple[dict, dict]:
    """执行一次请求（不轮换账号）。返回 (data, meta)。"""
    url, method, leftovers = build_request(api, params)
    if leftovers:
        raise ValueError(
            "缺少必填参数 %s（接口 %s）" % (", ".join(leftovers), api.get("id"))
        )
    headers = {"User-Agent": config.KPL_UA}
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    t0 = time.time()
    raw = http.request(url, method=method, headers=headers, data=b"", timeout=TIMEOUT)
    meta = {"api": api.get("id"), "url": redact(url), "method": method,
            "account": params.get("Account"), "elapsed_ms": int((time.time() - t0) * 1000)}
    rp = (raw or "").strip()
    if not rp:
        return {"_meta": meta, "empty": True}, meta
    try:
        data = http.load_json(rp)
    except ValueError:
        return {"_meta": meta, "raw": rp[:8000]}, meta
    if isinstance(data, dict):
        data.setdefault("_meta", {}).update(meta)
    return data, meta


def errcode(data) -> str:
    if isinstance(data, dict):
        return str(data.get("errcode", data.get("errCode", "0")) or "0")
    return "0"


def is_ok(data) -> bool:
    return errcode(data) in ("0", "00", "")


def soft_empty(data) -> bool:
    return errcode(data) in SOFT_ERRCODES


def rows(data) -> list:
    """粗取列表数据：命中第一个列表型字段（List/info/data/...）。

    开盘啦 `info` 常见形态为 `[行数组, 日期]`（无表头），此处自动解包到行数组。
    """
    v: list = []
    if isinstance(data, list):
        v = data
    elif isinstance(data, dict):
        for key in ("List", "list", "info", "Info", "data", "Data", "rows", "Rows", "items"):
            if isinstance(data.get(key), list):
                v = data[key]
                break
    else:
        return []
    if (v and isinstance(v[0], list)
            and (len(v) == 1 or not isinstance(v[1], (list, dict)))):
        return v[0]
    return v


def call(api_id: str, params: dict | None = None, *, account: str | None = None,
         rotate: bool = True) -> dict:
    """调用开盘啦官方接口；凭证失效自动切下一个内置账号。"""
    api = catalog.find(api_id)
    accs = config.accounts()
    if not accs:
        raise RuntimeError("未找到开盘啦账号（检查 %s 或环境变量 KPL_TOKEN/KPL_USER_ID）" % config.accounts_ini_path())
    if account:
        accs = [a for a in accs if a.name == account] or accs
    name_hint = (params or {}).get("account") or account
    if name_hint:
        ordered = [a for a in accs if a.name == name_hint] + [a for a in accs if a.name != name_hint]
        accs = ordered
    else:
        accs = config.rotate_order(accs)   # 主动轮换：两个全功能账号交替打头

    errors: list[str] = []
    tried = accs if rotate else accs[:1]
    for acc in tried:
        ph = acc.placeholders(Account=acc.name)
        merged = merge_params(api_id, {k: v for k, v in (params or {}).items() if k != "account"}, ph)
        try:
            data, meta = fetch(api, merged)
        except (http.HttpError, http.NetError, ValueError) as e:
            errors.append("%s: %s" % (acc.name, e))
            continue
        code = errcode(data)
        if code in ROTATE_ERRCODES:
            errors.append("%s: errcode=%s %s" % (acc.name, code, data.get("errmsg") or data.get("msg") or ""))
            continue
        if not is_ok(data) and not soft_empty(data):
            msg = data.get("errmsg") or data.get("msg") or code
            raise RuntimeError("开盘啦 %s errcode=%s %s（%s）" % (api_id, code, msg, acc.name))
        if isinstance(data, dict):
            data.setdefault("_meta", {})["account"] = acc.name
        if not name_hint and rotate:
            config.bump_account_cursor()   # 成功即推进游标 → 下一次换另一个账号
        return data
    raise RuntimeError("开盘啦 %s 全部账号失败: %s" % (api_id, " | ".join(errors)))


# 开盘啦涨停池（daily_limit_realtime / daily_limit_history）行内列位（无表头）。
# 已核对：0 代码 / 1 名称 / 4 时间戳 / 5 板块 / 6 封单额 / 11 成交额 / 12 题材 /
#         13 流通额 / 14 换手 / 18 连板文案 / 19 板块代码 / 21 最新价 / 22 涨幅%
KPL_ZT_COLS = {
    0: "code", 1: "name", 4: "time", 5: "plate", 6: "seal_amount", 11: "amount",
    12: "theme", 13: "circ_value", 14: "turnover", 18: "boards_text",
    19: "plate_code", 21: "price", 22: "pct_chg",
}


def _is_header_row(row) -> bool:
    """判断是否表头行：含非数字文本，且第 0 列不是 6 位股票代码。"""
    if not isinstance(row, (list, tuple)) or not row:
        return False
    if not any(isinstance(x, str) and str(x).strip() and not str(x).strip().isdigit()
               for x in row):
        return False
    c0 = str(row[0]).strip()
    return not (c0.isdigit() and len(c0) == 6)


def table(data, key: str | None = None, cols: dict | None = None) -> list[dict]:
    """把开盘啦二维数组转成 list[dict]。

    cols：列位 → 字段名映射（用于无表头接口，如涨停池）；未映射的列命名为 f<列号>。
    无 cols 时：若首行是表头行则按表头取名，否则原样返回 dict 行。
    """
    if key:
        raw = (data or {}).get(key) if isinstance(data, dict) else None
        raw = raw if isinstance(raw, list) else []
    else:
        raw = rows(data)
    if not raw:
        return []
    if all(isinstance(r, dict) for r in raw):
        return [dict(r) for r in raw]
    if cols:
        out: list[dict] = []
        for r in raw:
            if not isinstance(r, (list, tuple)):
                continue
            d = {cols.get(i, "f%d" % i): v for i, v in enumerate(r)}
            code = str(d.get("code") or "").strip().zfill(6)
            if not (code.isdigit() and len(code) == 6):
                continue
            d["code"] = code
            out.append(d)
        return out
    if _is_header_row(raw[0]):
        hdr = [str(x).strip() for x in raw[0]]
        out = []
        for r in raw[1:]:
            if not isinstance(r, (list, tuple)):
                continue
            out.append({h: (r[i] if i < len(r) else None) for i, h in enumerate(hdr) if h})
        return out
    return [r for r in raw if isinstance(r, dict)]
