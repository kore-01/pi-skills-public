#!/usr/bin/env python3
"""Cloudflare REST calls with credential handling taken off the caller's hands.

Two credential shapes exist and they are not interchangeable:

  Global API Key  32 or 37 chars  ->  X-Auth-Email + X-Auth-Key   (whole account)
  API Token       40 chars        ->  Authorization: Bearer        (scoped)

Sending the wrong one returns "6003 Invalid request headers / 6111 Invalid
format for Authorization header", which reads like a bad key when it is really a
wrong header. So the header set is chosen from the credential's own shape.

The key file is free-form Chinese text with the label glued to the value, so it
is parsed by shape (longest url-safe run on the line is the value) rather than by
fixed offsets.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

API_ROOT = "https://api.cloudflare.com/client/v4"
DEFAULT_KEY_FILE = Path("D:/PI/cloudflare-key.txt")
PROXY = "http://127.0.0.1:30001"

RUN_RE = re.compile(r"[A-Za-z0-9_\-]{20,}")
HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def mask(value: str) -> str:
    """Show enough to tell credentials apart, never enough to use one."""
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:8]}...{value[-4:]}"


def load_accounts(key_file: Path = DEFAULT_KEY_FILE) -> list[dict]:
    """Parse the credential file into one dict per account."""
    if not key_file.exists():
        raise SystemExit(f"key file not found: {key_file}")

    accounts: list[dict] = []
    current: dict | None = None

    for raw in key_file.read_text(encoding="utf-8", errors="replace").splitlines():
        text = raw.strip()
        if not text:
            continue

        # A user line opens a block; its first address is the login email.
        if "用户" in text or ("@" in text and "密码" not in text and "帐户" not in text):
            emails = EMAIL_RE.findall(text)
            if emails:
                current = {
                    "email": emails[0],
                    "zones_hint": emails,
                    "account_id": None,
                    "global_api_key": None,
                    "token": None,
                }
                accounts.append(current)
                continue
        if current is None:
            continue
        if "密码" in text:
            continue

        runs = RUN_RE.findall(text)
        if not runs:
            continue
        value = max(runs, key=len)
        label = text[: text.index(value)].strip(" :：.。\t-")

        if HEX32_RE.match(value) and ("帐户" in text or "account" in text.lower()):
            current["account_id"] = value
        elif "Global" in label or "global" in label:
            current["global_api_key"] = value
        elif len(value) == 40 and current["token"] is None:
            current["token"] = value
        elif current["global_api_key"] is None and len(value) in (32, 37):
            current["global_api_key"] = value

    return [a for a in accounts if a.get("account_id")]


def auth_headers(account: dict) -> list[str]:
    """Pick the header shape the credential actually is.

    A 40-character value is an API Token and goes in a Bearer header. Anything
    else is treated as a Global API Key, which needs the email alongside it.
    """
    token = account.get("token")
    if token and len(token) == 40:
        return [f"Authorization: Bearer {token}"]
    key = account.get("global_api_key")
    if key:
        return [f"X-Auth-Email: {account['email']}", f"X-Auth-Key: {key}"]
    raise SystemExit("no usable credential for this account")


def call(account: dict, method: str, path: str, body: str | None, raw: bool) -> tuple[int, dict | str]:
    """Perform one API request. Returns (http status, parsed body or text)."""
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    args = ["curl.exe", "-s", "-w", "\n%{http_code}", "--max-time", "60"]
    if PROXY:
        args += ["-x", PROXY]
    for header in auth_headers(account):
        args += ["-H", header]
    args += ["-X", method]
    if body is not None:
        if raw:
            args += ["--data-binary", body, "-H", "Content-Type: text/plain"]
        else:
            args += ["--data-binary", body, "-H", "Content-Type: application/json"]
    args.append(url)

    proc = subprocess.run(args, capture_output=True)
    text = proc.stdout.decode("utf-8", errors="replace")
    if "\n" in text:
        payload, _, status = text.rpartition("\n")
    else:
        payload, status = text, "0"

    try:
        return int(status or 0), json.loads(payload)
    except json.JSONDecodeError:
        return int(status or 0), payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Cloudflare REST call.")
    parser.add_argument("method")
    parser.add_argument("path")
    parser.add_argument("body", nargs="?")
    parser.add_argument("--account", type=int, default=1, help="1-based index from the key file")
    parser.add_argument("--raw", action="store_true", help="send body as text/plain (KV values)")
    parser.add_argument("--json", action="store_true", help="pretty-print the response")
    args = parser.parse_args(argv)

    accounts = load_accounts()
    if not accounts:
        print("  ✗ no account parsed from the key file", file=sys.stderr)
        return 2
    if not 1 <= args.account <= len(accounts):
        print(f"  ✗ --account {args.account} out of range (have {len(accounts)})", file=sys.stderr)
        return 2

    account = accounts[args.account - 1]
    status, payload = call(account, args.method.upper(), args.path, args.body, args.raw)

    if isinstance(payload, dict):
        ok = payload.get("success")
        if args.json or not ok:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif ok:
            result = payload.get("result")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print(payload)
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
