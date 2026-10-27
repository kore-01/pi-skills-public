#!/usr/bin/env python3
"""Tavily search over a rotating pool of API keys.

Every request leases a key from `rotation.py`, which hands them out strictly in
file order and advances a shared pointer on disk. This is what lets N concurrent
searches draw N different keys instead of all picking key 1 and tripping the
same rate limit: the lease is taken before the HTTP call, under a file lock, so
two threads cannot receive the same credential.

Errors split into two kinds, and the split is the whole retry policy:

  credential faults - the key itself is unusable (invalid, exhausted, still
  rate-limited after its own backoff). The key is quarantined for the rest of
  the cycle and the request retries on the next one. Because quarantined keys
  come back next cycle, a key that was merely throttled rejoins once the window
  passes.

  request faults - the query is wrong, or Tavily is down. Retrying on another
  key would just burn quota, so these propagate.

Usage:

    python scripts/search.py "query"
    python scripts/search.py "query" --depth advanced --max-results 10 --full
    python scripts/search.py "query" --topic news
    python scripts/search.py "q1" "q2" "q3" --concurrency 3
    python scripts/search.py --batch queries.json
    python scripts/search.py --status
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rotation import KeyPoolError, Lease, Rotator  # noqa: E402

ENDPOINT = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 45.0

# Tavily reports credential problems as 401/403/429/432/433. 432 is an
# exhausted plan and 433 a key that hit its rate ceiling; both mean "this key is
# done for now", which is exactly what quarantine expresses. 5xx is the service,
# not the key.
CREDENTIAL_STATUS = {401, 403, 429, 432, 433}

# How many different keys one request may try before giving up. With 269 keys, a
# handful is plenty: needing more means the pool itself is sick.
MAX_KEY_ATTEMPTS = 8

# Backoff for a 429 before we treat the key as quarantined. A short sleep often
# clears a per-second limit without burning the key for the whole cycle.
RATE_LIMIT_BACKOFF_SECONDS = 1.5


class SearchError(RuntimeError):
    """A failure the caller should see, not paper over with another key."""


@dataclass
class SearchResult:
    query: str
    answer: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 0
    keys_used: int = 0
    error: str | None = None


def _post(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - diagnostics must never mask the real error
        return ""


def search_one(
    query: str,
    rotator: Rotator,
    *,
    depth: str = "basic",
    max_results: int = 5,
    include_answer: bool = True,
    topic: str = "general",
    timeout: float = DEFAULT_TIMEOUT,
    sleep=time.sleep,
) -> SearchResult:
    """Run one query, rotating keys on credential faults."""
    payload = {
        "query": query,
        "search_depth": depth,
        "max_results": max_results,
        "include_answer": include_answer,
        "topic": topic,
    }
    tried: set[int] = set()
    result = SearchResult(query=query)

    for attempt in range(1, MAX_KEY_ATTEMPTS + 1):
        try:
            lease: Lease = rotator.acquire()
        except KeyPoolError as exc:
            result.error = str(exc)
            return result
        if lease.index in tried:
            # The pointer wrapped onto a key this request already used. That
            # happens only when most of the pool is quarantined, so stop rather
            # than loop.
            rotator.release(lease)
            result.error = result.error or "no unused key left in the pool"
            return result
        tried.add(lease.index)
        result.attempts = attempt
        result.keys_used = len(tried)

        try:
            response = _post(ENDPOINT, payload, lease.api_key, timeout)
        except urllib.error.HTTPError as exc:
            status = exc.code
            detail = _read_error(exc)
            if status in CREDENTIAL_STATUS:
                if status == 429:
                    sleep(RATE_LIMIT_BACKOFF_SECONDS * attempt)
                rotator.quarantine(lease, reason=f"http-{status}")
                result.error = f"HTTP {status}"
                continue
            rotator.release(lease)
            raise SearchError(f"HTTP {status}: {detail[:300]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Network faults belong to neither side. Give the key back without
            # blaming it, so a flaky link does not drain the pool.
            rotator.release(lease)
            raise SearchError(f"network: {exc}") from None

        rotator.release(lease)
        result.answer = response.get("answer")
        result.results = response.get("results") or []
        result.error = None
        return result

    result.error = result.error or "every key failed"
    return result


def _compact(result: SearchResult, full: bool) -> dict:
    """Shape the payload for an agent's context.

    The default keeps title, url, snippet, score and published_date — enough to
    cite and judge relevance. `--full` returns Tavily's raw fields, including
    `raw_content`.
    """
    if full:
        return {
            "query": result.query,
            "answer": result.answer,
            "results": result.results,
            "meta": {"attempts": result.attempts, "keys_used": result.keys_used},
        }
    compact = []
    for item in result.results:
        compact.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("content"),
                "score": item.get("score"),
                "published_date": item.get("published_date"),
            }
        )
    return {
        "query": result.query,
        "answer": result.answer,
        "results": compact,
        "meta": {
            "attempts": result.attempts,
            "keys_used": result.keys_used,
            "error": result.error,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search the web with Tavily.")
    parser.add_argument("queries", nargs="*", help="one or more queries")
    parser.add_argument("--batch", help="JSON array of queries or {query:...} objects")
    parser.add_argument("--depth", choices=["basic", "advanced"], default="basic")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--full", action="store_true", help="include raw_content")
    parser.add_argument("--status", action="store_true", help="pool health and exit")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

    rotator = Rotator()

    if args.status:
        print(json.dumps(rotator.status(), ensure_ascii=False, indent=2))
        return 0

    queries: list[str] = list(args.queries)
    if args.batch:
        try:
            with open(args.batch, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": f"batch read failed: {exc}"}, ensure_ascii=False))
            return 2
        if isinstance(payload, dict):
            payload = [payload]
        for item in payload or []:
            if isinstance(item, str):
                queries.append(item)
            elif isinstance(item, dict) and item.get("query"):
                queries.append(str(item["query"]))

    if not queries:
        parser.print_help()
        return 2

    results: list[SearchResult] = []
    if args.concurrency > 1 and len(queries) > 1:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [
                pool.submit(
                    search_one,
                    query,
                    rotator,
                    depth=args.depth,
                    max_results=args.max_results,
                    topic=args.topic,
                )
                for query in queries
            ]
            for future in futures:
                results.append(future.result())
    else:
        for query in queries:
            results.append(
                search_one(
                    query,
                    rotator,
                    depth=args.depth,
                    max_results=args.max_results,
                    topic=args.topic,
                )
            )

    payload = [_compact(result, args.full) for result in results]
    print(json.dumps(payload[0] if len(payload) == 1 else payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
