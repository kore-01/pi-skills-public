#!/usr/bin/env python3
"""Install the Tavily key file where `rotation.py` reads it.

`rotation.py` resolves the key file per platform:

    env TAVILY_KEY_FILE            (highest)
    D:\PI\tavily-keys.txt           (Windows)
    ~/.hermes/credentials/tavily-keys.txt   (Linux, including the phone sandbox)

On the phone the Linux path is the one that matters, and `~` is inside the
sandbox home, which is writable. So the default target is correct already and
this script only has to place the file there and lock it down.

The keys never appear in the output. `269 keys` is reported as a count, and the
fingerprint of each key is a truncated sha256 so two runs can be compared
without exposing anything.

Supply the keys in whichever way is convenient:

    # one per line on stdin
    printf 'tvly-xxx\ntvly-yyy\n' | python setup_keys.py

    # or a file
    python setup_keys.py --from-file /path/to/tavily-keys.txt

    # or an env var (practical for a modest number of keys)
    TAVILY_KEYS='tvly-xxx,tvly-yyy' python setup_keys.py
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

DEFAULT_TARGET = Path("~/.hermes/credentials/tavily-keys.txt").expanduser()


def digest(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:12]


def parse_keys(text: str) -> list[str]:
    """One key per line; blank lines and # comments are ignored."""
    keys = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            keys.append(stripped)
    return keys


def harden(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the Tavily key pool.")
    parser.add_argument("--target", type=Path, default=None, help="output path")
    parser.add_argument("--from-file", type=Path, help="read keys from a file")
    parser.add_argument("--status", action="store_true", help="report the current pool and exit")
    args = parser.parse_args(argv)

    target = args.target or Path(os.environ.get("TAVILY_KEY_FILE") or DEFAULT_TARGET)
    target = target.expanduser()

    if args.status:
        if not target.is_file():
            print(f"key file not found: {target}")
            return 1
        keys = parse_keys(target.read_text(encoding="utf-8", errors="replace"))
        print(f"key file : {target}")
        print(f"keys    : {len(keys)}")
        for index, key in enumerate(keys[:3], 1):
            print(f"  [{index}] sha256:{digest(key)}")
        if len(keys) > 3:
            print(f"  ... {len(keys) - 3} more")
        return 0

    # ---- collect ----------------------------------------------------------
    if args.from_file:
        if not args.from_file.is_file():
            raise SystemExit(f"source file not found: {args.from_file}")
        raw = args.from_file.read_text(encoding="utf-8", errors="replace")
    elif os.environ.get("TAVILY_KEYS"):
        raw = os.environ["TAVILY_KEYS"].replace(",", "\n")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raw = ""

    keys = parse_keys(raw)
    if not keys:
        print("no keys supplied.", file=sys.stderr)
        print("  use --from-file, TAVILY_KEYS, or pipe them on stdin.", file=sys.stderr)
        return 1

    # ---- write ------------------------------------------------------------
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(keys) + "\n"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    harden(tmp)
    tmp.replace(target)
    harden(target)

    print(f"wrote {len(keys)} key(s) to {target} (mode 600)")
    for index, key in enumerate(keys[:3], 1):
        print(f"  [{index}] sha256:{digest(key)}")
    if len(keys) > 3:
        print(f"  ... {len(keys) - 3} more")
    print()
    print("verify the pool:")
    print(f"  python {Path(__file__).parent / 'rotation.py'} status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
