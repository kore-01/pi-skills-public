# -*- coding: utf-8 -*-
"""kore_mint — 铸造 Kore 长效 access Token（owner 自用）+ 终身权益授予 + 双机镜像 + 校验。

原理（已核对 kore-auth-server 源码）：
  * `src/auth/jwt.js::verifyAccessToken` 只校验 HS256 签名 + `iss=kore-auth` + `aud=kore-client` + `type=access`
  * `src/auth/middleware.js::assertAccessSession`：**不带 `sid` 的 access 直接放行** → 不会「同端互踢」
  * `requireAuth → loadActiveUser(sub)`：要求 `users.status='active'`
  * py.590 / i.590 侧 `kpl_fetch/auth_gate.py::verify_token` = 远程 `GET <AUTH_BASE>/api/auth/me`（同一套校验）
  * 权益：`user_feature_subscriptions.expires_at > now` → consume 走 `subscription` 模式且**不扣次**

安全：本模块不内置任何密钥。JWT_SECRET 与 SSH 口令只从环境变量 / 命令行读取。
    真实 Token 只写入 `assets/py_token.txt`（或 --out 指定文件），禁止写进文档/commit。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config

EXP_MAX = 4102444800  # 2100-01-01T00:00:00Z
FEATURES_FILE = config.ASSETS_DIR / "features.lifetime.txt"

PRIMARY = {  # 主库机（212：m.590.net / py.590.net 回源）
    "host": os.environ.get("KORE_CN_SSH_HOST", "193.112.101.212"),
    "port": int(os.environ.get("KORE_CN_SSH_PORT", "5522")),
    "user": os.environ.get("KORE_CN_SSH_USER", "root"),
    "password": os.environ.get("KORE_CN_SSH_PASSWORD") or os.environ.get("KORE_SSH_PASSWORD_CN") or "",
    "env": "/opt/kore-auth/.env",
}
BACKUP = {  # 备库机（55：i.590.net / k.590.net 回源）
    "host": os.environ.get("KORE_BACKUP_SSH_HOST", "111.170.173.55"),
    "port": int(os.environ.get("KORE_BACKUP_SSH_PORT", "5522")),
    "user": os.environ.get("KORE_BACKUP_SSH_USER", "root"),
    "password": os.environ.get("KORE_BACKUP_SSH_PASSWORD") or "",
    "env": "/opt/kore-auth/.env",
}

VERIFY_HOSTS = ("https://m.590.net", "https://k.590.net", "https://py.590.net", "https://i.590.net")


class MintError(RuntimeError):
    pass


# ---------------------------------------------------------------- JWT
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign_access(sub: int, username: str, role: str, secret: str, exp: int = EXP_MAX,
                iat: int | None = None, sid: str | None = None) -> str:
    """手工 HS256 签发 access token（零依赖）。sid=None → 免同端互踢。"""
    payload = {
        "sub": int(sub),
        "username": str(username),
        "role": str(role or "user"),
        "type": "access",
        "iss": "kore-auth",
        "aud": "kore-client",
        "iat": int(iat if iat is not None else time.time()),
        "exp": int(exp),
    }
    if sid:
        payload["sid"] = str(sid)
    head = {"alg": "HS256", "typ": "JWT"}
    seg = "%s.%s" % (
        _b64u(json.dumps(head, separators=(",", ":")).encode()),
        _b64u(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()),
    )
    sig = hmac.new(secret.encode("utf-8"), seg.encode("utf-8"), hashlib.sha256).digest()
    return "%s.%s" % (seg, _b64u(sig))


def decode_payload(token: str) -> dict:
    try:
        seg = token.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------- HTTP
def http_json(url: str, token: str = "", method: str = "GET", body: dict | None = None,
              timeout: float = 25.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "kpls-kore-mint/1.0")
    req.add_header("X-App-Name", config.PY_APP_NAME)
    req.add_header("X-Client-Kind", "web")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return int(resp.status), (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return int(exc.code), json.loads(raw or "{}")
        except Exception:  # noqa: BLE001
            return int(exc.code), {"_raw": raw[:300]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"_err": "%s: %s" % (type(exc).__name__, str(exc)[:160])}


# ---------------------------------------------------------------- SSH / DB
def _ssh(cfg: dict):
    try:
        import paramiko  # 可选依赖：仅 --from-ssh / --grant / --mirror 需要
    except ImportError as exc:  # pragma: no cover
        raise MintError("需要 paramiko 才能走 SSH（pip install paramiko），或改用 --secret 直接提供 JWT_SECRET") from exc
    if not cfg.get("password"):
        raise MintError("缺少 SSH 口令：设置环境变量 KORE_CN_SSH_PASSWORD / KORE_BACKUP_SSH_PASSWORD")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(cfg["host"], port=cfg["port"], username=cfg["user"], password=cfg["password"],
                look_for_keys=False, allow_agent=False, timeout=30)
    cli.get_transport().set_keepalive(30)
    return cli


def _run(cli, cmd: str, timeout: int = 120) -> str:
    _, out, err = cli.exec_command(cmd, timeout=timeout)
    return (out.read() + err.read()).decode("utf-8", "replace").strip()


def _mysql_wrap(cfg: dict) -> str:
    """用远端 .env 里的库凭据执行 mysql，避免在命令行留密码。"""
    return 'set -a; . %s; mysql -h127.0.0.1 -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"' % cfg["env"]


def read_jwt_secret(cfg: dict | None = None) -> str:
    cfg = cfg or PRIMARY
    cli = _ssh(cfg)
    try:
        out = _run(cli, "grep -E '^JWT_SECRET=' %s" % cfg["env"])
    finally:
        cli.close()
    for line in out.splitlines():
        if line.startswith("JWT_SECRET="):
            secret = line.split("=", 1)[1].strip()
            if len(secret) >= 32:
                return secret
    raise MintError("未从 %s 读取到 JWT_SECRET" % cfg["host"])


def feature_ids() -> list[str]:
    """默认终身授权清单（assets/features.lifetime.txt，一行一个）。"""
    if FEATURES_FILE.is_file():
        ids = [ln.strip() for ln in FEATURES_FILE.read_text(encoding="utf-8-sig").splitlines()]
        return [i for i in ids if i and not i.startswith("#")]
    return []


def read_subscriptions(cfg: dict, user_id: int) -> list[tuple[str, int, str | None]]:
    cli = _ssh(cfg)
    try:
        sql = ("SELECT feature_id, expires_at, subscription_sku FROM user_feature_subscriptions "
               "WHERE user_id=%d ORDER BY feature_id;" % int(user_id))
        out = _run(cli, '%s -N -B -e "%s"' % (_mysql_wrap(cfg), sql))
    finally:
        cli.close()
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not line.lower().startswith("mysql:"):
            sku = parts[2] if len(parts) > 2 and parts[2] != "NULL" else None
            rows.append((parts[0], int(parts[1]), sku))
    return rows


def grant(cfg: dict, user_id: int, ids: list[str], exp_ms: int = EXP_MAX * 1000,
          sku: str = "lifetime") -> str:
    if not ids:
        raise MintError("授权清单为空：先写 assets/features.lifetime.txt 或传 --features")
    now_ms = int(time.time() * 1000)
    vals = ",".join("(%d,'%s',%d,'%s',%d)" % (int(user_id), f, exp_ms, sku, now_ms) for f in ids)
    sql = ("INSERT INTO user_feature_subscriptions (user_id, feature_id, expires_at, subscription_sku, updated_at) "
           "VALUES %s ON DUPLICATE KEY UPDATE expires_at=VALUES(expires_at), "
           "subscription_sku=VALUES(subscription_sku), updated_at=VALUES(updated_at);" % vals)
    cli = _ssh(cfg)
    try:
        return _run(cli, "cat > /tmp/kore_mint_grant.sql <<'SQLEOF'\n%s\nSQLEOF\n%s < /tmp/kore_mint_grant.sql && echo GRANT_OK"
                    % (sql, _mysql_wrap(cfg)))
    finally:
        cli.close()


def mirror(primary: dict | None = None, backup: dict | None = None, user_id: int = 1) -> dict:
    """把主机已生效的权益行镜像到备机（双机互备：两台资料需一致）。"""
    primary, backup = primary or PRIMARY, backup or BACKUP
    rows = read_subscriptions(primary, user_id)
    if not rows:
        raise MintError("主库 %s 上 user_id=%s 无权益行" % (primary["host"], user_id))
    cli = _ssh(backup)
    try:
        before = len(read_subscriptions(backup, user_id))
        sql = ("INSERT INTO user_feature_subscriptions (user_id, feature_id, expires_at, subscription_sku, updated_at) "
               "VALUES %s ON DUPLICATE KEY UPDATE expires_at=VALUES(expires_at), "
               "subscription_sku=VALUES(subscription_sku), updated_at=VALUES(updated_at);"
               % ",".join("(%d,'%s',%d,%s,%d)" % (user_id, f, exp, "'%s'" % sku if sku else "NULL", int(time.time() * 1000))
                          for f, exp, sku in rows))
        out = _run(cli, "cat > /tmp/kore_mint_mirror.sql <<'SQLEOF'\n%s\nSQLEOF\n%s < /tmp/kore_mint_mirror.sql && echo MIRROR_OK"
                   % (sql, _mysql_wrap(backup)))
    finally:
        cli.close()
    after = len(read_subscriptions(backup, user_id))
    return {"rows_source": len(rows), "backup_before": before, "backup_after": after, "out": out}


# ---------------------------------------------------------------- 校验
def verify(token: str, hosts: tuple[str, ...] = VERIFY_HOSTS) -> list[str]:
    out = []
    for host in hosts:
        st, data = http_json(host + "/api/auth/features", token=token)
        feats = data.get("features") if isinstance(data, dict) else None
        kf = next((f for f in feats if f.get("featureId") == "kpl.fetch"), None) if isinstance(feats, list) else None
        active = (kf or {}).get("subscriptionActive")
        out.append("features %-22s st=%-3s n=%-3s kpl.fetch.active=%s sku=%s" % (
            host, st, (len(feats) if isinstance(feats, list) else "-"), active, (kf or {}).get("subscriptionSku")))
        if host.endswith(("py.590.net", "i.590.net")):
            st2, d2 = http_json(host + "/api/list", token=token)
            n = len((d2.get("apis") or d2.get("list") or [])) if isinstance(d2, dict) else None
            out.append("/api/list %-21s st=%-3s n=%s" % (host, st2, n))
    return out

def _human_left(exp: int, now: int) -> str:
    left = exp - now
    if left <= 0:
        return "已过期"
    days = left // 86400
    return ("%d 天" % days) if days < 3650 else ("%.0f 年" % (days / 365.0))


def _get_json_retry(url: str, token: str, tries: int = 2) -> tuple[int, dict]:
    """带一次重试的 GET（i.590.net 偶发 TLS 握手失败，重试即恢复）。"""
    st, data = http_json(url, token=token)
    for _ in range(max(0, tries - 1)):
        if st == 200:
            break
        time.sleep(1.0)
        st, data = http_json(url, token=token)
    return st, data


def check_token_file(path: Path | None = None) -> tuple[bool, list[str]]:
    """只读体检：Token 文件/声明 + 四域权益 + 两机 `/api/list`。不发 SSH、不写库。"""
    p = Path(path or (config.ASSETS_DIR / "py_token.txt"))
    if not p.is_file():
        return False, ["token 文件缺失：%s" % p]
    token = p.read_text(encoding="utf-8-sig").strip()
    if token.count(".") != 2:
        return False, ["token 形态异常（不是 JWT）：%s" % p]

    pay = decode_payload(token)
    now = int(time.time())
    exp = int(pay.get("exp") or 0)
    lines: list[str] = []
    ok = True
    if pay.get("type") != "access" or pay.get("iss") != "kore-auth":
        ok = False
    if exp <= now:
        ok = False
    if pay.get("sid"):
        ok = False  # 带 sid 会互踢：长效 Token 必须无 sid
    iat = int(pay.get("iat") or 0)
    max_age = int(os.environ.get("KORE_TOKEN_MAX_AGE_DAYS") or "365")
    age_days = int((now - iat) / 86400) if iat else 0
    if max_age > 0 and iat and age_days >= max_age:
        ok = False  # 到期策略：默认满 365 天自动换新（KORE_TOKEN_MAX_AGE_DAYS=0 关闭）
    lines.append("token %s len=%s sub=%s user=%s exp=%s 剩余=%s sid=%s 已用=%s天/阈值%s天" % (
        p.name, len(token), pay.get("sub"), pay.get("username"), exp,
        _human_left(exp, now), pay.get("sid") or "无", age_days, (max_age or "∞")))

    for host in VERIFY_HOSTS:
        st, data = _get_json_retry(host + "/api/auth/features", token)
        feats = data.get("features") if isinstance(data, dict) else None
        kf = None
        if isinstance(feats, list):
            kf = next((f for f in feats if isinstance(f, dict) and f.get("featureId") == "kpl.fetch"), None)
        active = bool((kf or {}).get("subscriptionActive"))
        if st != 200 or not active:
            ok = False
        lines.append("features %-22s st=%-3s n=%-3s kpl.fetch.active=%s sku=%s" % (
            host, st, (len(feats) if isinstance(feats, list) else "-"), active, (kf or {}).get("subscriptionSku")))
        if host.endswith(("py.590.net", "i.590.net")):
            st2, d2 = _get_json_retry(host + "/api/list", token)
            n2 = len((d2.get("apis") or d2.get("list") or [])) if isinstance(d2, dict) else 0
            if st2 != 200 or n2 < 100:
                ok = False
            lines.append("/api/list %-21s st=%-3s n=%s" % (host, st2, n2))
    return ok, lines



# ---------------------------------------------------------------- CLI
def main(args) -> int:
    """kpls kore-mint：铸造 + 授权 + 镜像 + 校验。"""
    user_id = int(getattr(args, "user_id", 1))
    username = getattr(args, "username", "") or "e07559"
    role = getattr(args, "role", "") or "admin"
    exp = int(getattr(args, "exp", 0) or EXP_MAX)
    out_path = Path(getattr(args, "out", "") or (config.ASSETS_DIR / "py_token.txt"))
    # 0) --check / --auto：只读体检；--auto 仅在不健康时才轮换（定时任务入口）
    want_check = bool(getattr(args, "check", False))
    want_auto = bool(getattr(args, "auto", False))
    if want_check or want_auto:
        healthy, lines0 = check_token_file(out_path)
        for ln in lines0:
            print("[check] " + ln)
        if healthy:
            print("[check] 健康：Token 有效 + 四域权益有效 + 两机目录可用（未做任何写入）")
            return 0
        if not want_auto:
            print("[check] 不健康：如确需轮换，用 --auto 或 --from-ssh --grant-all --mirror --verify")
            return 2
        print("[auto] 体检不通过 → 自动轮换（重铸 + 授权 + 镜像 + 校验）")
        args.from_ssh = True
        args.grant_all = True
        args.mirror = True
        args.verify = True


    # 1) 铸造
    secret = getattr(args, "secret", "") or os.environ.get("KORE_JWT_SECRET", "")
    if not secret and getattr(args, "from_ssh", False):
        secret = read_jwt_secret()
        print("[secret] 已从 %s 读取 JWT_SECRET（len=%d）" % (PRIMARY["host"], len(secret)))
    if not secret:
        raise MintError("缺 JWT_SECRET：设置环境变量 KORE_JWT_SECRET，或用 --from-ssh，或 --secret")
    token = sign_access(user_id, username, role, secret, exp=exp)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(token + "\n", encoding="utf-8", newline="")
    pay = decode_payload(token)
    print("[mint] sub=%s(%s) role=%s exp=%s sid=%s len=%d → %s" % (
        user_id, username, role, exp, pay.get("sid", "无"), len(token), out_path))

    # 2) 授权 / 镜像（可选）
    ids = []
    if getattr(args, "features", ""):
        ids = [x.strip() for x in str(args.features).replace("，", ",").split(",") if x.strip()]
    if getattr(args, "grant_all", False):
        ids = ids or feature_ids()
        print("[grant] 主机 %s 授权 %d 个 feature" % (PRIMARY["host"], len(ids)))
        print(_run_grant(PRIMARY, user_id, ids))
    if getattr(args, "mirror", False):
        print("[mirror]", json.dumps(mirror(user_id=user_id), ensure_ascii=False)[:300])

    # 3) 校验
    if getattr(args, "verify", False):
        for line in verify(token):
            print("[verify] " + line)
    return 0


def _run_grant(cfg: dict, user_id: int, ids: list[str]) -> str:
    return grant(cfg, user_id, ids)
