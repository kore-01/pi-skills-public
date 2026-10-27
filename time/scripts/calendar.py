#!/usr/bin/env python3
"""A-share trading calendar: is the market open today, and when was the last close?

Answers the question "is this a trading day?" that the clock alone cannot. The
clock knows it is Sunday; it does not know Sunday is a working day this week,
and it does not know Monday is a holiday.

Two lists drive everything, both from the exchange-published 2026 calendar
(沪深北交易所 2025-12-22 发布 + 国务院办公厅通知, archived in the knowledge
base at D:\\cf\\knowledge\\22-kpl-py\\2026-A股节假日.json):

  HOLIDAYS - statutory closures. The market does not open.
  MAKEUP   - 调休补班日. A weekend day the exchange works anyway, so it IS a
             trading day. Getting this backwards is the classic error: skipping
             a Saturday that is actually a trading session, or treating one as
             a close.

A weekday outside both lists is a trading day. That is the whole rule.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

# Statutory closures for 2026. 25 days.
HOLIDAYS_2026 = (
    "2026-01-01", "2026-01-02", "2026-01-03",
    "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
    "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23",
    "2026-04-04", "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-09-25", "2026-09-26", "2026-09-27",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05",
    "2026-10-06", "2026-10-07",
)

# 调休补班日 - weekend days the exchange works. Still trading days. 7 days.
MAKEUP_DAYS_2026 = (
    "2026-01-05",
    "2026-02-24",
    "2026-04-07",
    "2026-05-06",
    "2026-06-22",
    "2026-09-28",
    "2026-10-08",
)

# Regular session, Beijing time. Used to say which part of the day we are in.
SESSIONS = (
    ("集合竞价", "09:15", "09:25"),
    ("早盘", "09:30", "11:30"),
    ("午间休市", "11:30", "13:00"),
    ("午盘", "13:00", "15:00"),
    ("盘后固定价格交易", "15:05", "15:30"),
    ("已收盘", "15:30", "09:15"),
)

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def parse(value: str) -> date:
    return date.fromisoformat(value)


def is_holiday(day: date) -> bool:
    return day.isoformat() in HOLIDAYS_2026


def is_makeup(day: date) -> bool:
    return day.isoformat() in MAKEUP_DAYS_2026


def is_trading_day(day: date) -> bool:
    """The one rule: statutory closure loses, makeup work wins, else weekday."""
    if is_holiday(day):
        return False
    if is_makeup(day):
        return True
    return day.weekday() < 5


def why(day: date) -> str:
    if is_holiday(day):
        return "法定节假日休市"
    if is_makeup(day):
        return "调休补班日（周末照常交易）"
    if day.weekday() < 5:
        return "普通工作日"
    return "周末休市"


def next_trading_day(day: date, limit: int = 60) -> date | None:
    for offset in range(1, limit + 1):
        candidate = day + timedelta(days=offset)
        if is_trading_day(candidate):
            return candidate
    return None


def prev_trading_day(day: date, limit: int = 60) -> date | None:
    for offset in range(1, limit + 1):
        candidate = day - timedelta(days=offset)
        if is_trading_day(candidate):
            return candidate
    return None


def trading_days_between(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        if is_trading_day(cursor):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def session_of(day: date, hour: int, minute: int) -> str:
    """Which part of the session `hour:minute` falls in, Beijing time."""
    now_minutes = hour * 60 + minute
    for name, start, end in SESSIONS:
        start_h, start_m = (int(part) for part in start.split(":"))
        end_h, end_m = (int(part) for part in end.split(":"))
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes <= now_minutes < end_minutes:
            return name
    return "已收盘"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-share trading calendar.")
    parser.add_argument("--date", help="judge this YYYY-MM-DD instead of today")
    parser.add_argument("--json", action="store_true", help="structured output")
    parser.add_argument(
        "--last-close",
        action="store_true",
        help="the most recent completed session before the given date",
    )
    parser.add_argument(
        "--count",
        type=int,
        metavar="N",
        help="list the next N trading days from the given date",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

    today = parse(args.date) if args.date else date.today()

    if args.count:
        days = []
        cursor = today
        while len(days) < args.count:
            if is_trading_day(cursor):
                days.append(cursor)
            cursor += timedelta(days=1)
        if args.json:
            print(json.dumps([d.isoformat() for d in days], ensure_ascii=False))
        else:
            for d in days:
                print(f"{d.isoformat()} {WEEKDAY_NAMES[d.weekday()]}")
        return 0

    if args.last_close:
        last = prev_trading_day(today)
        if args.json:
            print(json.dumps({"date": last.isoformat() if last else None}, ensure_ascii=False))
        elif last:
            print(f"{last.isoformat()} {WEEKDAY_NAMES[last.weekday()]}")
        else:
            print("未找到")
        return 0

    trading = is_trading_day(today)
    nxt = next_trading_day(today)
    prv = prev_trading_day(today)
    hour, minute = 0, 0
    if not args.date:
        from datetime import datetime

        now = datetime.now()
        hour, minute = now.hour, now.minute

    if args.json:
        payload = {
            "date": today.isoformat(),
            "weekday": WEEKDAY_NAMES[today.weekday()],
            "is_trading_day": trading,
            "reason": why(today),
            "session": session_of(today, hour, minute) if trading else None,
            "next_trading_day": nxt.isoformat() if nxt else None,
            "prev_trading_day": prv.isoformat() if prv else None,
            "holidays_total": len(HOLIDAYS_2026),
            "makeup_days_total": len(MAKEUP_DAYS_2026),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    weekday = WEEKDAY_NAMES[today.weekday()]
    status = "交易日" if trading else "非交易日"
    print(f"{today.isoformat()} {weekday} {status} - {why(today)}")
    if trading and not args.date:
        print(f"当前时段: {session_of(today, hour, minute)}")
    if prv:
        print(f"上一交易日: {prv.isoformat()}")
    if nxt:
        print(f"下一交易日: {nxt.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
