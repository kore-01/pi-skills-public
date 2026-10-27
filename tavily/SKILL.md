---
name: tavily
description: >-
  Search the live web through Tavily (https://www.tavily.com/) over a pool of
  rotating API keys. Use this whenever a task needs current information from
  the internet — news, prices, company facts, documentation versions, "what
  happened recently", "latest", "search for", fact-checking a claim against
  sources, or any question where training data would be stale or
  unverifiable. Also use when a previous answer needs citations, or when you
  must confirm something happened after your training cutoff. Prefer this over
  guessing or over a plain fetch: Tavily returns ranked results with excerpts
  and an answer. Handles 269 keys with strict round-robin so concurrent
  searches never collide on one credential.
---

# Tavily

Search the web. The point of this skill is not the HTTP call — it is the key
pool underneath, which turns 269 free-tier dev keys into one pool with roughly
269× the quota, and keeps concurrent searches from all trampling key 1.

## Why the rotation matters

A single Tavily dev key allows about 1,000 searches a month. With one key you
run out quickly; with 269 you effectively do not. But the moment you search in
parallel, the naive approach — "use the first key" — sends every thread at the
same credential and trips its rate limit, so the parallelism buys nothing.

So keys are handed out **strictly in file order, one per request**, from a
pointer on disk shared by every process:

```
request 1 → key[0]     request 270 → key[0]   (cycle 2)
request 2 → key[1]     ...
request 269 → key[268]
```

Each full cycle gives every key exactly one use, so the load is even. N parallel
searches draw N *different* keys, which is what makes concurrency safe.

When a key fails for a reason the key owns — invalid, out of quota, still
rate-limited after its own backoff — it is removed **for the rest of the cycle only** and the request retries on the next key. It rejoins at the start of the next cycle. That asymmetry matters: a permanently dead key would shrink the pool forever, while a key that never left would be drawn, fail, and force its neighbour to absorb the retry.

## Searching

```bash
python scripts/search.py "查询内容"
python scripts/search.py "查询内容" --max-results 10 --depth advanced
python scripts/search.py "查询内容" --topic news          # news | finance | general
python scripts/search.py "q1" "q2" "q3" --concurrency 3   # parallel,不同 key
python scripts/search.py --batch queries.json             # JSON 数组
python scripts/search.py --status                          # 池子健康度
```

`--batch` accepts either a JSON array of strings or a list of `{"query": "..."}`
objects.

Default output is trimmed for a model's context: `title`, `url`, `snippet`,
`score`, `published_date`, plus Tavily's `answer` when available, plus a `meta`
block showing how many keys and attempts the query needed. Add `--full` when
the excerpt is not enough and you want Tavily's raw fields, including
`raw_content`.

## Choosing arguments

| Need | Flag |
|---|---|
| Quick factual lookup | 默认 `--depth basic`, `--max-results 5` |
| Deep research, comparison, hard question | `--depth advanced --max-results 10` |
| Breaking news, dated events | `--topic news` |
| Market or company data | `--topic finance` |
| Need the whole page text | `--full` |
| Independent sub-questions | 多个 query + `--concurrency N` |

Concurrency is capped by the pool, not by the machine: keep `--concurrency` at
or below the number of available keys (`--status` prints it). Past that you
start queueing on keys you already used.

## Reading the result

`meta.attempts > 1` means earlier keys failed and were skipped — normal, and it
is why a search can succeed even with dead keys in the file. `meta.error` being
non-null means the query itself failed after trying up to eight distinct keys;
report that rather than inventing an answer.

Cite what you use. Tavily returns `url` for every result; an answer without a
source is a guess wearing a citation's clothes.

## Managing the pool

```bash
python scripts/rotation.py status        # 指针、圈数、隔离数、失败统计
python scripts/rotation.py next 5        # 预演接下来 5 个 key（不消耗配额）
python scripts/rotation.py reset         # 清空指针/隔离，从 key[0] 重新开始
```

The key file is resolved per platform — `TAVILY_KEY_FILE` if set, else
`D:\PI\tavily-keys.txt` on Windows, else `~/.hermes/credentials/tavily-keys.txt`
on Linux. One key per line, read fresh on every lease so you can add keys without restarting anything. Adding or removing keys
resets the cycle automatically — the stored pointer would otherwise point into a
different pool and skew the balance.

State lives in `state/rotation.json` next to this file. It holds the pointer,
the cycle number, the quarantine set and per-key failure counts; safe to delete
to start clean (that is what `reset` does).

## Failure modes worth knowing

| Symptom | Meaning | What happens |
|---|---|---|
| `meta.attempts` climbing to 8 | Most keys are dead or throttled | Check `--status`; the `failures` block names the keys |
| `HTTP 401` on every key | Keys are wrong or the file is stale | Regenerate keys at tavily.com |
| `HTTP 432` | Plan quota exhausted | Key quarantined; the cycle moves on |
| `HTTP 429` | Rate limited | One short backoff, then quarantined for the cycle |
| Search returns nothing useful | Query too broad or wrong `--topic` | Reformulate; try `advanced` depth |

## What this skill does not do

- It does not scrape pages or bypass a paywall. Tavily returns what its index
  already has; for full text on a specific URL, fetch it separately.
- It does not cache results. Every call spends quota, so do not re-run an
  identical query in a loop.
- It cannot tell whether the web is right. Sources disagree; report the
  disagreement rather than picking the convenient side.
