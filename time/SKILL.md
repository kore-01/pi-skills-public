---
name: time
description: Read the real current date and time before any time-sensitive analysis, and check the A-share trading calendar. Use whenever an answer depends on "now" — stock and market analysis, quarterly or annual reports, earnings seasons, "latest" data, recent news, scheduled tasks, or anything that compares a date against today. Also use for timezone conversion between A-share (UTC+8), Japan, US and UK market hours. Run scripts/now.py and scripts/calendar.py instead of answering from memory.
---

# Time

## Why this skill exists

A model's training cutoff is not the present. Every date recalled from memory
is a guess, and a guess in a stock analysis is not a small error — it decides
which fiscal year you read, whether a report is "recent", whether the market is
open, and whether "latest" means this quarter or three years ago.

So the rule is one line: **never answer a time-sensitive question from memory.
Run the script.**

```
python scripts/now.py
2026-10-18 04:31:26 星期日 UTC+08:00 | UTC 2026-10-17 20:31:26 | epoch 1792269086
```

## The clock

Run it **first**, before any other tool, when the task involves:

- Any relative date: today, yesterday, this week, this month, this quarter, YTD
- Any "latest / recent / current / newest" claim
- Annual, semi-annual or quarterly reports (年报 / 中报 / 季报) — which period is
  published *now* depends entirely on the real date
- Earnings seasons (一季报 Apr, 中报 Aug, 三季报 Oct, 年报 Apr)
- Anything scheduled, dated, or expiring
- Comparing a data timestamp against "now" — is this feed stale?

Run it again if a long analysis spans a session boundary, or if the user
corrects your sense of the date.

```bash
python scripts/now.py                  # one line, for a pipeline
python scripts/now.py --utc            # 2026-10-17T20:31:26Z
python scripts/now.py --iso            # local ISO-8601 with offset
python scripts/now.py --json           # local + UTC + epoch + 4 markets
```

`--json` gives you the local date, time, weekday and offset; the UTC instant; an
epoch; and the current wall-clock time in the four markets this skill covers
(A-share/HK, Japan, US, UK). Output is UTF-8 on every platform, so piping it into
a JSON parser is safe.

No dependencies beyond the standard library, and it reads the machine clock — no
network, so it works offline and cannot be poisoned by a stale cache.

## The calendar: is the market open?

The clock knows it is Sunday. It does not know this Sunday is a working day, and
it does not know next Monday is a holiday. That is what `calendar.py` answers.

```
python scripts/calendar.py
2026-10-18 周日 非交易日 - 周末休市
上一交易日: 2026-10-16
下一交易日: 2026-10-19
```

The data is transcribed from the knowledge base
(`D:\cf\knowledge\22-kpl-py\2026-A股节假日.json`, from the 沪深北交易所
2025-12-22 announcement). Two lists drive it:

- `HOLIDAYS_2026` — 33 statutory closure days. The market does not open.
- `MAKEUP_DAYS_2026` — 7 调休补班日. A weekend the exchange works anyway, so it
  **is** a trading day. This is the direction people get wrong: skipping a
  Saturday that is actually a session, or calling one a close.

The whole rule: a holiday loses, a makeup day wins, anything else is a trading
day iff it is a weekday.

```bash
python scripts/calendar.py                       # today, plain
python scripts/calendar.py --json                # structured, with next/prev
python scripts/calendar.py --date 2026-10-08     # judge any date
python scripts/calendar.py --last-close          # most recent completed session
python scripts/calendar.py --count 10            # the next 10 trading days
```

`--json` carries `is_trading_day`, a plain-language `reason`, the current
`session`, and both neighbouring trading days — enough to state an analysis date
and the last close in one call.

Re-verify the transcription against the knowledge base when the year rolls over;
the exchange publishes the next calendar each December.

## What to do with the result

State the anchor explicitly, so the user can see what you reasoned from:

> 分析基准时间：2026-10-18（星期日）北京时间 04:31，UTC+08:00；非交易日，上一交易日 2026-10-16

Then reason from that, not from your training cutoff. Three habits follow:

**Derive the reporting period from the real date.** In October, the most recent
published annual report is for the previous fiscal year, and the third-quarter
report is the one landing now. Do not assume a year.

**Never call a non-trading day's price "today's close".** Use `--last-close` and
name that date. Around 国庆 and 春节 the gap is a week or more, and the difference
between "yesterday's close" and "the last close" is the difference between a
valid backtest and a fabricated one.

**Say which session the market is in.** A-share hours are 09:15-09:25 集合竞价,
09:30-11:30 早盘, 13:00-15:00 午盘, 15:05-15:30 盘后固定价格交易. Outside those
windows, and on non-trading days, there is no live price to report.

## What this skill does not know

- It does not know 停牌 (suspension) lists, half-days, or ad-hoc exchange
  announcements. A suspended stock still has a trading day on the calendar. If
  whether a specific stock traded matters, say so and ask.
- It does not predict anything. It reports the present, nothing more.
- Market offsets are fixed (no DST). Good enough to tell which session a
  timestamp falls in; not a substitute for a real timezone database if you need
  exact US or UK wall-clock conversion during DST transitions.
- The calendar covers 2026 only.
