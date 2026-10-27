# -*- coding: utf-8 -*-
"""kpls.config — 配置解析（开盘啦 2 账号 / Tushare Pro / 平台 py.590 Token / 双机地址）。

解析优先级（先命中先用，绝不硬编码在代码里）：
  开盘啦账号库  env KPL_ACCOUNTS_INI → D:\cf\kpl\config\kpl_accounts.ini → <skill>/assets/kpl_accounts.ini
  开盘啦单账号  env KPL_TOKEN/KPL_USER_ID/KPL_DEVICE_ID（兜底，单账号无 failover）
  Tushare Token env TUSHARE_TOKEN → ini[s:tushare] → D:\cf\趋势分析\.env → <skill>/assets/tushare.token
  平台 Token    env KPL_PY_TOKEN/KPL_EXPORT_TOKEN/KPL_KORE_TOKEN → <skill>/assets/py_token.txt → ini[s:py590]

注意（手机沙盒）：ASSETS_DIR 由 __file__ 推导，因此把技能整体复制到可写目录后，
凭据放在副本的 assets/ 里即可生效，无需改代码。/skills 本身是只读挂载。
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
CATALOG_FILE = Path(os.environ.get("KPLS_CATALOG") or (ASSETS_DIR / "apis.json"))

_KPL_INI_DEFAULT = Path(r"D:\cf\kpl\config\kpl_accounts.ini")
_KPL_ENV_DEFAULT = Path(r"D:\cf\kpl\.env")
_TS_ENV_DEFAULT = Path(r"D:\cf\趋势分析\.env")

KPL_UA = "Dalvik/2.1.0 (Linux; U; Android 14; V2178A Build/UP1A.231005.007)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_APP_VER = "6.2.30.3"
DEFAULT_APIV = "w47"
DEFAULT_LIST_TYPE = "4"

# py.590.net(212 机) 与 i.590.net(55 机) 同数据互备，按序 failover
PY_HOSTS_DEFAULT = ["https://py.590.net", "https://i.590.net"]
PY_HOST_IP = {"https://py.590.net": "193.112.101.212", "https://i.590.net": "111.170.173.55"}
PY_APP_NAME = "kpl-py"


def data_dir() -> Path:
    """缓存/落盘目录（默认 <skill>/var，可用 KPLS_DATA_DIR 覆盖）。"""
    raw = os.environ.get("KPLS_DATA_DIR")
    p = Path(raw) if raw else SKILL_DIR / "var"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class Account:
    """开盘啦官方接口账号（Token/UserID/DeviceID 走 query string）。"""

    name: str
    user_id: str
    token: str
    device_id: str
    label: str = ""
    list_type: str = DEFAULT_LIST_TYPE
    app_ver: str = DEFAULT_APP_VER
    apiv: str = DEFAULT_APIV
    source: str = ""

    @property
    def masked_token(self) -> str:
        t = self.token or ""
        return (t[:6] + "..." + t[-4:]) if len(t) > 12 else "***"

    def placeholders(self, **override: str) -> dict[str, str]:
        ph = {
            "Token": self.token,
            "UserID": str(self.user_id),
            "DeviceID": self.device_id,
            "VerSion": self.app_ver or DEFAULT_APP_VER,
            "apiv": self.apiv or DEFAULT_APIV,
            "PhoneOSNew": "1",
            "Type": self.list_type,
        }
        ph.update({k: str(v) for k, v in override.items() if v not in (None, "")})
        return ph

    def info(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "token": self.masked_token,
            "app_ver": self.app_ver,
            "apiv": self.apiv,
            "list_type": self.list_type,
            "source": self.source,
        }


def read_env_file(path: Path, keys: tuple[str, ...] = ()) -> dict[str, str]:
    """读 KEY=VALUE 形式的 env 文件（容忍引号/空格/注释）。"""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not keys or k in keys:
            out[k] = v
    return out


def accounts_ini_path() -> Path | None:
    for cand in (
        Path(os.environ["KPL_ACCOUNTS_INI"]) if os.environ.get("KPL_ACCOUNTS_INI") else None,
        _KPL_INI_DEFAULT,
        ASSETS_DIR / "kpl_accounts.ini",
    ):
        if cand and cand.is_file():
            return cand
    return None


def _load_ini_accounts(ini: Path) -> list[Account]:
    cp = configparser.ConfigParser()
    try:
        cp.read(ini, encoding="utf-8-sig")
    except (OSError, configparser.Error):
        return []
    out: list[Account] = []
    for sec in cp.sections():
        s = cp[sec]
        tok = (s.get("token") or "").strip()
        uid = (s.get("user_id") or "").strip()
        if not tok or not uid:
            continue
        out.append(
            Account(
                name=sec.strip(),
                user_id=uid,
                token=tok,
                device_id=(s.get("device_id") or "").strip(),
                label=(s.get("label") or "").strip(),
                list_type=(s.get("list_type") or DEFAULT_LIST_TYPE).strip(),
                app_ver=(s.get("app_ver") or DEFAULT_APP_VER).strip(),
                apiv=(s.get("apiv") or DEFAULT_APIV).strip(),
                source=str(ini),
            )
        )
    return out


_ACCOUNT_CACHE: list[Account] | None = None


def accounts(reload: bool = False) -> list[Account]:
    """内置开盘啦账号列表（默认主账号优先，用于 failover）。"""
    global _ACCOUNT_CACHE
    if _ACCOUNT_CACHE is not None and not reload:
        return list(_ACCOUNT_CACHE)

    out: list[Account] = []
    ini = accounts_ini_path()
    if ini:
        out = _load_ini_accounts(ini)
    if not out:
        env = read_env_file(_KPL_ENV_DEFAULT)
        env.update({k: v for k, v in os.environ.items() if k.startswith("KPL_")})
        tok = (env.get("KPL_TOKEN") or os.environ.get("KPL_TOKEN") or "").strip()
        uid = (env.get("KPL_USER_ID") or os.environ.get("KPL_USER_ID") or "").strip()
        if tok and uid:
            out = [
                Account(
                    name="main_self",
                    user_id=uid,
                    token=tok,
                    device_id=(env.get("KPL_DEVICE_ID") or "").strip(),
                    list_type=(env.get("KPL_TYPE") or DEFAULT_LIST_TYPE).strip(),
                    source="env",
                )
            ]

    preferred = [x.strip() for x in (os.environ.get("KPLS_ACCOUNTS") or "").split(",") if x.strip()]
    if preferred:
        order = {n: i for i, n in enumerate(preferred)}
        out = [a for a in out if a.name in order]
        out.sort(key=lambda a: order[a.name])
    else:
        out.sort(key=lambda a: (0 if a.name == "main_self" else 1, a.name))

    _ACCOUNT_CACHE = out
    return list(out)


def tushare_token() -> str:
    """Tushare Pro token 解析。"""
    for key in ("TUSHARE_TOKEN", "TS_TOKEN"):
        if os.environ.get(key):
            return os.environ[key].strip()
    tok = (read_env_file(_KPL_ENV_DEFAULT, ("TUSHARE_TOKEN", "TS_TOKEN")).get("TUSHARE_TOKEN") or "").strip()
    if tok:
        return tok
    for key in ("TUSHARE_TOKEN", "TS_TOKEN", "token"):
        tok = (read_env_file(_TS_ENV_DEFAULT).get(key) or "").strip()
        if tok:
            return tok
    f = ASSETS_DIR / "tushare.token"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            s = line.strip().lstrip("\ufeff").strip()
            if s and not s.startswith("#"):
                return s
    return ""


def py_token() -> str:
    """平台（py.590.net）Bearer Token：Kore access JWT 或当日 kpl_export_token。"""
    for key in ("KPL_PY_TOKEN", "KPL_EXPORT_TOKEN", "KPL_KORE_TOKEN"):
        if os.environ.get(key):
            return os.environ[key].strip()
    f = ASSETS_DIR / "py_token.txt"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            s = line.strip().lstrip("\ufeff").strip()
            if s and not s.startswith("#"):
                return s
    ini = accounts_ini_path()
    if ini:
        cp = configparser.ConfigParser()
        try:
            cp.read(ini, encoding="utf-8-sig")
            for sec in ("py590", "py.590", "platform"):
                if cp.has_section(sec) and cp.get(sec, "token", fallback="").strip():
                    return cp.get(sec, "token").strip()
        except (OSError, configparser.Error):
            pass
    return ""


def py_hosts() -> list[str]:
    raw = [h.strip().rstrip("/") for h in (os.environ.get("KPL_PY_HOSTS") or "").split(",") if h.strip()]
    return raw or list(PY_HOSTS_DEFAULT)


def doctor() -> dict:
    """环境自检：账号/Tushare/平台 Token 的可用性（不发起网络请求）。"""
    accs = accounts()
    return {
        "skill_dir": str(SKILL_DIR),
        "accounts_ini": str(accounts_ini_path() or ""),
        "catalog": str(CATALOG_FILE),
        "catalog_exists": CATALOG_FILE.is_file(),
        "accounts": [a.info() for a in accs],
        "accounts_ok": bool(accs),
        "accounts_has_2": len(accs) >= 2,
        "tushare_token": bool(tushare_token()),
        "py_token": bool(py_token()),
        "py_hosts": py_hosts(),
        "data_dir": str(data_dir()),
    }


# ---------------------------------------------------------------- 账号轮换
def rotation_enabled() -> bool:
    """多账号主动轮换开关（env `KPLS_ACCOUNT_ROTATE`，默认开；设 0 回到"主账号优先"）。"""
    v = (os.environ.get("KPLS_ACCOUNT_ROTATE") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _cursor_file() -> Path:
    return data_dir() / "account_cursor"


def account_cursor() -> int:
    try:
        return int((_cursor_file().read_text(encoding="utf-8").strip() or "0"))
    except (OSError, ValueError):
        return 0


def bump_account_cursor(step: int = 1) -> int:
    """调用成功后推进游标 → 下次请求从另一个账号起，均摊频率、避开单号限流换号码。"""
    nxt = account_cursor() + int(step)
    try:
        _cursor_file().write_text(str(nxt), encoding="utf-8")
    except OSError:
        pass
    return nxt


def rotate_order(accs: list[Account]) -> list[Account]:
    """按持久化游标轮换起始账号；`KPLS_ACCOUNT_ROTATE=0` 或单账号时保持原序。"""
    if len(accs) < 2 or not rotation_enabled():
        return list(accs)
    k = account_cursor() % len(accs)
    return list(accs[k:]) + list(accs[:k])
