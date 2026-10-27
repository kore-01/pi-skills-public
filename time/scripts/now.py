#!/usr/bin/env python3
"""Current time for an agent that must not guess it.

A model's training cutoff is not the present. Any analysis that reasons about
"today", "this quarter", "the latest session" or "since the last earnings" is
wrong the moment it borrows a date from memory, so this script exists to make
the real clock cheap to ask for.

Prints one line by default, so it composes in a pipeline:

    python now.py
    2026-10-18 04:28:36 Sunday +08:00 | UTC 2026-10-17 20:28:36 | epoch 1760738916

Use --json for structured output, --utc for the single timestamp every other
zone is derived from, and --iso for a local ISO-8601 string with offset.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

# Chinese weekday names, because the analyses this supports are written in
# Chinese. The ISO date stays unambiguous in any locale.
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# The markets this script gets asked about. Fixed UTC offsets only, so it needs
# no tzdata installed; DST drift is not worth a dependency for a clock read.
MARKET_ZONES = (
    ("Asia/Shanghai", "A-share / Hong Kong", 8),
    ("Asia/Tokyo", "Japan", 9),
    ("America/New_York", "US", -4),
    ("Europe/London", "UK", 1),
)


def offset_label(seconds: int) -> str:
    """`28800` -> `UTC+08:00`, `-14400` -> `UTC-04:00`."""
    sign = "+" if seconds >= 0 else "-"
    total = abs(seconds) // 60
    return f"UTC{sign}{total // 60:02d}:{total % 60:02d}"


def build(moment: datetime) -> dict:
    """Everything a caller might need, in one plain dict."""
    local = moment.astimezone()
    utc = moment.astimezone(timezone.utc)
    offset = local.utcoffset() or timedelta(0)
    return {
        "local": {
            "datetime": local.strftime("%Y-%m-%d %H:%M:%S"),
            "date": local.strftime("%Y-%m-%d"),
            "time": local.strftime("%H:%M:%S"),
            "weekday": WEEKDAYS[local.weekday()],
            "weekday_number": local.isoweekday(),
            "utc_offset": offset_label(int(offset.total_seconds())),
        },
        "utc": {
            "datetime": utc.strftime("%Y-%m-%d %H:%M:%S"),
            "iso": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "epoch_seconds": int(moment.timestamp()),
        "markets": [
            {
                "zone": zone,
                "label": label,
                "datetime": (utc + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S"),
                "utc_offset": offset_label(hours * 3600),
            }
            for zone, label, hours in MARKET_ZONES
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the real current time.")
    parser.add_argument("--json", action="store_true", help="structured output")
    parser.add_argument("--utc", action="store_true", help="only the UTC timestamp")
    parser.add_argument("--iso", action="store_true", help="local ISO-8601 with offset")
    args = parser.parse_args(argv)

    # A Windows console leaves stdout on the ANSI code page (GBK here), so the
    # Chinese weekday bytes would leave as GBK and break any UTF-8 reader
    # downstream. Force UTF-8 so `--json` is parseable everywhere.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

    info = build(datetime.now(timezone.utc))

    if args.utc:
        print(info["utc"]["iso"])
    elif args.iso:
        print(datetime.fromisoformat(info["local"]["datetime"]).isoformat(sep="T"))
    elif args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        local = info["local"]
        print(
            f"{local['datetime']} {local['weekday']} {local['utc_offset']}"
            f" | UTC {info['utc']['datetime']}"
            f" | epoch {info['epoch_seconds']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
