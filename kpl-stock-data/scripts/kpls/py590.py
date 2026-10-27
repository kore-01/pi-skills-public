# -*- coding: utf-8 -*-
"""kpls.py590 — 平台接口（https://py.590.net 与 http://i.590.net 同数据互备，自动 failover）。

鉴权：
  Authorization: Bearer <token>     +  X-App-Name: kpl-py
  token = Kore access JWT（约 15 分钟）或当日 scoped `kpl_export_token`（当日 23:59:59 前有效）
  免登录：/、/health；其余（/apis.json、/api/list、/api/info/*、/api/get/*、/api/*/board）需登录
  计费：/api/get/* 走 illa 模式按次扣次；/api/*/board（看板）与 /api/l2-brief、/api/get/st_* 不扣次

目录：assets/apis.json 内 py.590.local 条目（30 条）+ EXTRA_BOARDS（serve_http.py 路由整理）
"""
from __future__ import annotations

import time
from urllib.parse import urlsplit

from . import catalog, config, http


class PlatformError(RuntimeError):
    def __init__(self, msg: str, status: int = 0):
        self.status = status
        super().__init__(msg)


class TokenRequired(PlatformError):
    pass


class EntitlementRequired(PlatformError):
    pass


TOKEN_HINT = (
    "缺少平台 Token。获取方式（任选其一）：\n"
    "  1) 环境变量：$env:KPL_PY_TOKEN='<token>'\n"
    "  2) 文件：%s\\py_token.txt（写一行 token）\n"
    "  3) 当日导出：kpls py-export --kore-token <Kore登录JWT>  （POST /api/auth/export-token）\n"
    "未提供 Token 时请改用 Tier1 直连源：kpls kpl / ts / sn / em / l2"
) % str(config.ASSETS_DIR)


# ---------------------------------------------------------------- 路径与URL
def _path_of(api: dict) -> str:
    url = str(api.get("url") or "")
    if url.startswith("strategy://"):
        return "/api/get/" + str(api.get("id"))
    parts = urlsplit(url)
    return parts.path + (("?" + parts.query) if parts.query else "")


def board(endpoint: str, params: dict | None = None, **kw) -> dict:
    """调用看板/策略端点。endpoint 可以是接口 id、/api/... 路径或目录条目。"""
    entry = None
    try:
        entry = catalog.find(endpoint)
    except catalog.CatalogError:
        entry = None
    if entry is not None:
        return call(entry["id"], params, **kw)
    if endpoint in EXTRA_BOARDS:
        return call_path(EXTRA_BOARDS[endpoint], params, **kw)
    path = endpoint if str(endpoint).startswith("/") else ("/" + str(endpoint))
    return call_path(path, params, **kw)


def call_path(path: str, params: dict | None = None, *, token: str | None = None,
              method: str = "GET", timeout: float = 20.0, hosts: list[str] | None = None) -> dict:
    tok = token if token is not None else config.py_token()
    if not tok:
        raise TokenRequired(TOKEN_HINT)
    headers = {
        "Authorization": "Bearer %s" % tok,
        "X-App-Name": config.PY_APP_NAME,
        "Accept": "application/json",
        "User-Agent": config.BROWSER_UA,
    }
    hosts = [h.rstrip("/") for h in (hosts or config.py_hosts())]
    errors: list[str] = []
    for host in hosts:
        url = host + (path if path.startswith("/") else "/" + path)
        if params:
            url = http.qs(url, params)
        t0 = time.time()
        try:
            data = http.get_json(url, headers=headers, timeout=timeout, retries=0, encodings=("utf-8",))
        except http.HttpError as e:
            if e.status in (401, 403):
                errors.append("%s -> 401（Token 无效/过期）" % host)
                continue
            if e.status == 402:
                raise EntitlementRequired("402 需要权益（featureId/月卡/年卡）: %s" % (e.body or "")[:300], 402)
            snippet = (getattr(e, "body", "") or "").strip().replace("\n", " ")[:160]
            hint = PARAM_HINTS.get(path, "")
            errors.append("%s -> HTTP %s %s%s" % (host, e.status, snippet, (" 提示: " + hint) if hint else ""))
            continue
        except (http.NetError, ValueError) as e:
            errors.append("%s -> %s" % (host, e))
            continue
        if isinstance(data, dict):
            data.setdefault("_meta", {}).update(
                {"host": host, "path": path, "elapsed_ms": int((time.time() - t0) * 1000)}
            )
            if data.get("need_login") or str(data.get("error") or "") in ("UNAUTHORIZED", "unauthorized"):
                errors.append("%s -> need_login" % host)
                continue
        return data
    if errors and all("401" in e or "need_login" in e for e in errors):
        raise TokenRequired("Token 被拒（双机均 401）：%s\n%s" % ("; ".join(errors), TOKEN_HINT))
    raise PlatformError("平台双机均失败: %s" % "; ".join(errors))


def call(api_id: str, params: dict | None = None, **kw) -> dict:
    """按目录 id 调用平台接口（Tier2）。"""
    api = catalog.find(api_id)
    src = catalog.source_of(api)
    if src != "py590":
        raise PlatformError("接口 %s 不是平台端（source=%s），请用 kpls api/相应子命令" % (api_id, src))
    path = _path_of(api)
    merged = dict(params or {})
    base_q = urlsplit(str(api.get("url") or "")).query
    if base_q:
        import urllib.parse as _up

        for k, v in _up.parse_qsl(base_q, keep_blank_values=True):
            merged.setdefault(k, v)
    return call_path(path, merged, **kw)


def health(hosts: list[str] | None = None) -> dict:
    """/health 免登录，用于探测双机可用性。"""
    out = {}
    for host in [h.rstrip("/") for h in (hosts or config.py_hosts())]:
        try:
            data = http.get_json(host + "/api/health", timeout=10, retries=1, encodings=("utf-8",))
            out[host] = {"ok": True, "data": data, "ip": config.PY_HOST_IP.get(host, "")}
        except Exception as e:  # noqa: BLE001
            out[host] = {"ok": False, "error": str(e), "ip": config.PY_HOST_IP.get(host, "")}
    return out


def list_apis(*, token: str | None = None) -> list[dict]:
    """/api/list（需登录）——服务端目录（151 策略/看板 + apis.json 全量）。"""
    data = call_path("/api/list", token=token)
    if isinstance(data, dict):
        for key in ("apis", "list", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return data if isinstance(data, list) else []


def api_info(api_id: str, *, token: str | None = None) -> dict:
    data = call_path("/api/info/" + api_id, token=token)
    return data if isinstance(data, dict) else {}


def export_token(kore_token: str, *, save: bool = True) -> dict:
    """把 Kore 登录 JWT 换成当日有效的 scoped token（当日 23:59:59 前有效）。"""
    data = http.post_form(
        config.py_hosts()[0] + "/api/auth/export-token",
        {},
        headers={"Authorization": "Bearer %s" % kore_token, "X-App-Name": config.PY_APP_NAME},
    )
    parsed = http.load_json(data)
    tok = ""
    if isinstance(parsed, dict):
        tok = str(parsed.get("token") or (parsed.get("data") or {}).get("token") or "")
    if tok and save:
        (config.ASSETS_DIR / "py_token.txt").write_text(tok + "\n", encoding="utf-8")
    return {"ok": bool(tok), "saved": bool(tok and save), "token": (tok[:8] + "...") if tok else "", "raw": parsed}


def strategy_overview(codes: list[str] | str, day: str | None = None, *, token: str | None = None) -> dict:
    """策略统一指标接口（28 字段，供 6 个策略共用）。"""
    code_str = ",".join(codes) if isinstance(codes, (list, tuple)) else str(codes)
    return call_path("/api/strategy-overview", {"codes": code_str, "day": day} if day else {"codes": code_str},
                     token=token)


# 需要必填参数的看板（缺参会返回 400，这里给出提示）
PARAM_HINTS: dict[str, str] = {
    "/api/em-fflow/board": "需 code=<6 位股票代码>（或 symbol）",
    "/api/ths-bigorder/board": "需 code=<6 位股票代码>",
    "/api/plate-stocks/board": "需 plate=<板块ID>（如 801900）；可选 window=auction|am|day",
}


EXTRA_BOARDS: dict[str, str] = {
    # 天梯 / 情绪 / 板块
    "ladder/quant_pools": "/api/ladder/quant_pools",
    "ladder/plate-top5": "/api/ladder/plate-top5",
    "ladder/ticket_history": "/api/ladder/ticket_history",
    "ladder/watch": "/api/ladder/watch",
    "ladder/watch_l2": "/api/ladder/watch_l2",
    "auction-pool": "/api/auction-pool",
    "auction-buy-pool": "/api/auction-buy-pool",
    "auction-hist/days": "/api/auction-hist/days",
    "auction-hist/board": "/api/auction-hist/board",
    "mood/board": "/api/mood/board",
    "plate-stocks/board": "/api/plate-stocks/board",
    "zt-timeline/board": "/api/zt-timeline/board",
    "composite-select/board": "/api/composite-select/board",
    "surge-lowbuy-pool": "/api/surge-lowbuy-pool",
    "lhb-hist/days": "/api/lhb-hist/days",
    "lhb-hist/board": "/api/lhb-hist/board",
    # 资金 / L2
    "flow_batch": "/api/flow_batch",
    "flow_history": "/api/flow_history",
    "cyq": "/api/cyq",
    # 复盘聚合看板
    "premarket/board": "/api/premarket/board",
    "open_review/board": "/api/open_review/board",
    "intraday_pulse/board": "/api/intraday_pulse/board",
    "tail_snapshot/board": "/api/tail_snapshot/board",
    "close_review/board": "/api/close_review/board",
    "ladder/board": "/api/ladder/board",
    "broken-stocks/board": "/api/broken-stocks/board",
    "darktrade-fund/board": "/api/darktrade-fund/board",
    "em-fflow/board": "/api/em-fflow/board",
    "ths-bigorder/board": "/api/ths-bigorder/board",
    "kanpan/board": "/api/kanpan/board",
    "popularity/board": "/api/popularity/board",
    # 终身看盘（lifetime watch，2026-10-19 新增）
    "lifetime/overview": "/api/lifetime/watch/overview",
    "lifetime/ladder": "/api/lifetime/watch/ladder",
    "lifetime/stock": "/api/lifetime/watch/stock",
    "lifetime/quote": "/api/lifetime/watch/quote",
    "lifetime/days": "/api/lifetime/watch/days",
    "lifetime/status": "/api/lifetime/status",
    "lifetime/redeem": "/api/lifetime/redeem",
}


# ---------------------------------------------------------------- 终身看盘（lifetime watch）
def lifetime_overview(token=None):
    """实时总览：龙头池 + 涨停梯队 + 情绪（layers: 5板+~首板）。"""
    return call_path("/api/lifetime/watch/overview", token=token)


def lifetime_ladder(day=None, token=None):
    """历史涨停梯队（指定日全量，layers 按连板数分层）。"""
    return call_path("/api/lifetime/watch/ladder", {"date": day} if day else {}, token=token)


def lifetime_stock(code, token=None):
    """个股历史轨迹：梯队 track + 涨停命中 zt_hits + 资金流 flow。"""
    return call_path("/api/lifetime/watch/stock", {"code": code}, token=token)


def lifetime_quote(codes, token=None):
    """实时行情（新浪批量快照）。codes 为逗号分隔股票代码串或 list。"""
    c = ",".join(codes) if isinstance(codes, (list, tuple)) else str(codes)
    return call_path("/api/lifetime/watch/quote", {"codes": c}, token=token)


def lifetime_days(token=None):
    """归档交易日列表。"""
    return call_path("/api/lifetime/watch/days", token=token)


def lifetime_status(token=None):
    """终身授权状态（lifetime / userId / display）。"""
    return call_path("/api/lifetime/status", token=token)


def lifetime_redeem(code, token=None):
    """用兑换码（如 KPLT-xxx）兑换终身授权。"""
    return call_path("/api/lifetime/redeem", {"code": code}, token=token)
