---
name: recover-l2-from-precomputed-brief
description: Use when Linux pool L2 fields are empty or rate-limited despite an existing morning l2_brief file.
tags: ["自习"]
---

# Recover L2 from precomputed brief

Diagnose and fix empty pool L2 data by reusing the morning `l2_brief` artifact, while retaining wenap only as a fallback. This does not redesign the pool renderer or replace the upstream precompute job.

## When to Use

- `jlh.html` or `/api/pool` shows L2 values as `—` or empty.
- `l2_precompute.py` already produces a dated JSON file during the morning cron window.
- wenap calls are quota-limited, slow, or batch requests return only partial results.
- A previous L2 failure appears cached and is no longer retried.

Don't use for:
- Changing L2 scoring formulas or selection thresholds.
- Systems that do not already produce `l2_brief_YYYYMMDD.json`.
- Treating a successful API response as proof that the data source or fields are correct.

## Procedure

1. Locate the precompute artifact and confirm its schedule and shape on each target host:

   `find /opt -name 'l2_precompute*' 2>/dev/null | head -3`
   `crontab -l | grep -i l2 | head -5`
   `ls -la /www/wwwroot/chy/data/l2_brief_$(date +%Y%m%d).json`

   Verify the file is current, non-empty, and produced around the final precompute run. Do not assume the job is absent merely because an earlier path such as `/www/kpl-test/kpl-self/原始/l2_precompute.py` is missing.

2. Inspect the JSON structure before writing integration code:

   `python3`
   `d = json.load(open('/www/wwwroot/chy/data/l2_brief_20261021.json', encoding='utf-8'))`
   `items = d.get('items') or {}`
   `print(type(items).__name__, len(items), d.get('final'))`
   `print(items.get('301313'))`

   Expect `items` to be a dictionary keyed by six-digit stock code, not a list and not `by_code`. Check that entries contain the fields needed by `_l2_fields_from_item`, especially `tag`, `tip`, `suggest`, `headline`, `bullets`, `brief_md`, and `strength`. Confirm coverage for the requested pool before changing code.

3. Check whether `pool_enrich.py` imports or calls `enrich_l2_on_stocks` and whether the existing implementation uses a Windows-only path such as `D:\cf\kpl-direct-l2`. On Linux, make the local brief file the primary source, then use wenap only for missing codes. Preserve normalized six-digit code matching and return the same L2 field shape.

4. Ensure failed results are not treated as permanently valid cache entries. Cache successful enrichment separately from failures, or invalidate failures when the dated brief or upstream data changes, so a transient wenap failure does not suppress future retries.

5. If the UI has an L2-only refresh path, expose a focused endpoint/button that refreshes L2 without recomputing the whole pool. Keep ordinary refresh behavior unchanged. For export paths that may run after the pool was loaded, fetch the current pool once when the in-memory collection is empty before exporting; do not assume the initial render populated it.

6. Deploy the same tested code to every target host, then validate both APIs on each host:

   `curl -s -m 60 'http://127.0.0.1:39001/api/l2-refresh?force=1'`
   `curl -s -m 60 'http://127.0.0.1:39001/api/pool?force=1'`

   Inspect `meta.source`, `meta.hit`, `meta.miss`, and `meta.analyzed`. For full local-brief coverage, require `meta.source` to identify `l2_brief` and `meta.analyzed` to be `0`; require every requested stock to have a non-empty tag and mapped display fields.

7. Update the operational documentation with the artifact path, fallback rule, cache-failure behavior, endpoint, deployment hosts, and the verification evidence. Keep hostnames and dated symbols as examples rather than hard-coded requirements.

## Pitfalls

- **The wrong job path was checked first.** The precompute job may live under `/opt/chyl2/`, while the tested application path is `/www/kpl-test/kpl-self/原始/`. Search and inspect cron before concluding that no precompute exists.
- **Assuming the brief is a list or has `by_code`.** This artifact used `items` as a dictionary keyed by code; using `items[0]` raises `KeyError: 0`, and checking `by_code` falsely reports zero coverage.
- **A Linux Windows path makes L2 look unavailable.** A literal `D:\cf\kpl-direct-l2` path can make `bid_analysis` import fail on every Linux host. Detect platform/path assumptions and make the local Linux artifact path explicit.
- **Caching failure poisons recovery.** If `ok:false` results are persisted as cache hits, later runs may never retry. Only cache successful results or version/invalidate failure entries.
- **A nonempty file does not guarantee pool coverage.** Count requested codes against `items` and inspect the actual response; broad file size is insufficient.
- **`analyzed: 0` is only meaningful with a `l2_brief` source and complete hits.** It proves no fallback requests were needed, not merely that the endpoint returned successfully.
- **A late export can be empty because the render stopped fetching.** Re-fetch the collection when it is empty immediately before export, then verify the exported collection is nonempty.
- **Do not turn a successful syntax check into a success claim.** Require syntax validation, deployment on every host, and API-level field coverage.

## Verification

On each target host, both `/api/l2-refresh?force=1` and `/api/pool?force=1` return the expected pool codes with `meta.source` identifying `l2_brief`, `meta.hit` equal to the requested count, `meta.miss` equal to `0`, and `meta.analyzed` equal to `0` when the local file is complete; the UI/export also shows non-empty L2 tags.
