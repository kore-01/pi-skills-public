#!/usr/bin/env python3
"""List the Cloudflare accounts found in the credential file, masked.

The key file holds several accounts and, per account, more than one string that
looks like a secret. Printing them all is how secrets end up in a transcript, so
this shows only what is needed to tell them apart: the email, the account id,
and a masked fingerprint of each credential.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cf import DEFAULT_KEY_FILE, load_accounts, mask  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="List Cloudflare accounts.")
    parser.add_argument("--json", action="store_true", help="machine readable")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    args = parser.parse_args(argv)

    accounts = load_accounts(args.key_file)
    if not accounts:
        print("  ✗ 没有从 key 文件解析出账号", file=sys.stderr)
        return 1

    if args.json:
        safe = [
            {
                "index": i,
                "email": a["email"],
                "account_id": a["account_id"],
                "credential": "api_token" if a.get("token") else "global_api_key",
            }
            for i, a in enumerate(accounts, 1)
        ]
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        return 0

    for i, acc in enumerate(accounts, 1):
        kind = "API Token (Bearer)" if acc.get("token") else "Global API Key (X-Auth)"
        print(f"  [{i}] {acc['email']}")
        print(f"      account_id : {acc['account_id']}")
        print(f"      凭据类型   : {kind}")
        if acc.get("global_api_key"):
            print(f"      global_key : {mask(acc['global_api_key'])}")
        if acc.get("token"):
            print(f"      api_token  : {mask(acc['token'])}")
        if acc.get("zones_hint") and len(acc["zones_hint"]) > 1:
            print(f"      文件备注域 : {', '.join(acc['zones_hint'][1:])}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
