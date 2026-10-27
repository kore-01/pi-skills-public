---
name: nvidia-integrate-chat-benchmark
description: Use when ranking NVIDIA integrate.api chat models by content TTFT and dropping non-chat 404s.
tags: ["自习"]
---

# NVIDIA integrate chat benchmark

Rank NVIDIA `https://integrate.api.nvidia.com/v1/chat/completions` models with the read-only script `D:\cf\cursor-byok\benchmark_nvidia.py`, counting only body `content` as TTFT. This does not edit user channel config, and it does not treat a timeout or a catalog listing as proof a model is unusable or usable.

## When to Use

- User asks to test which NVIDIA models are fastest so the fast ones can be used.
- Need a CSV of TTFT / total_ms / tok_per_sec plus the failure reason distribution.
- A previous run called models slow or dead because of proxy, short timeout, or reasoning-token TTFT.

Don't use for:
- Writing `~/.cursor-local-assistant-v2/config.yaml`, `~/.ccursor/providers.json`, or `D:\opencode2api\config.json`. Default is read-only; a write needs a diff, explicit consent, a `*.bak-<timestamp>` backup, and whole-block edits (never delete a single `modelID` line).
- Proving OpenRouter or Cursor daemon health.
- Treating `agent --list-models` or a knowledge-doc commit as the benchmark result.

## Procedure

1. Work from the script directory. Confirm the script and result file exist before trusting an old CSV:

   `Set-Location D:\cf\cursor-byok`

   `Get-ChildItem 'D:\cf\cursor-byok\nvidia_speed.csv','D:\cf\cursor-byok\benchmark_nvidia.py'`

   Keys stay in `nvidia.txt` (gitignored). Do not copy key material into docs.

2. Full ranking, direct (no proxy). The script lists models (`GET /v1/models`), drops non-chat ids (embed / safety / guard / parse / translate / clip / rerank; observed 83 → 62), rotates keys from `nvidia.txt`, then does a short pass plus a slow retry at concurrency 1:

   `python benchmark_nvidia.py --keys-file nvidia.txt --runs 2 --timeout 60 --slow-timeout 200 --concurrency 2`

3. Single-model check:

   `python benchmark_nvidia.py --keys-file nvidia.txt --models "nvidia/nemotron-3-ultra-550b-a55b"`

4. Proxy comparison only when asked. Same model and key: direct was 4.0s / 5.2s; `http://127.0.0.1:30001` was 8.8s / 10.8s. Default runs stay direct:

   `python benchmark_nvidia.py --keys-file nvidia.txt --proxy http://127.0.0.1:30001`

5. Read the CSV in PowerShell, not by assuming the header row is the only truth:

   `Get-Content nvidia_speed.csv -Encoding UTF8 | Select-Object -First 12`

   `$csv = Import-Csv nvidia_speed.csv`

   `"总数 $($csv.Count) ; 成功 $(@($csv | Where-Object { $_.success -eq 'True' }).Count) ; 失败 $(@($csv | Where-Object { $_.success -ne 'True' }).Count)"`

   Observed full file: 62 rows, 6 `success=True`, 56 failures. Usable ranks were `meta/llama-3.2-11b-vision-instruct` (TTFT 561 ms), `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (1167 ms), `nvidia/nemotron-3-ultra-550b-a55b` (3662 ms), `openai/gpt-oss-20b` (7710 ms), `meta/muse-glimmer-30b` (24422 ms), `stepfun-ai/step-5-preview` (54388 ms). User-confirmed fast set that the short pass can still time out: `nvidia/nemotron-3-ultra-550b-a55b`, `deepseek-ai/deepseek-v4.1-flash`, `openai/gpt-oss-20b`, `z-ai/glm-5.3-flash`, `stepfun-ai/step-5-preview`. Prefer the user's live check over a timeout row.

6. If a knowledge note is required, add it under `D:\cf\knowledge\36-cursor-cli\` and one index row in that folder's `README.md`. Do not change channel YAML as part of publishing the ranking.

## Pitfalls

- **First SSE chunk is not TTFT.** nemotron streams `reasoning_content` before `content`. Counting the first chunk with a small `max_tokens` (16/64/512) looks fast while body text is empty. TTFT starts only at `delta["content"]`; record `reasoning_content` separately. If body text is empty, retry once at 4× `max_tokens` instead of marking the model dead.
- **Direct is faster than the local proxy here.** A 2× slower proxy run is not an NVIDIA outage. An older "NVIDIA needs the proxy" note used `stream:false` plus a small `max_tokens`.
- **Short timeout false-fails slow-but-alive models.** `stepfun-ai/step-5-preview` TTFT 54s and `meta/muse-glimmer-30b` TTFT 24s die on a 25–30s first pass. Use `--slow-timeout` before calling them unavailable. Timeout ≠ unusable when the user already got a completion (free-tier `503 ResourceExhausted` also causes this).
- **Concurrency lies.** Concurrency 4 timed `nemotron-3-ultra` at 2.2s while a solo run was 4.6s. Publish concurrency-1 numbers; concurrency 3 is only a coarse filter. Final conclusions must not come from the default coarse pass.
- **404 is not a bad key.** `HTTPStatusError: Client error '404 Not Found' for url 'https://integrate.api.nvidia.com/v1/chat/completions'` means that catalog id has no chat endpoint (46 of 56 failures). Do not rotate keys to "fix" it.
- **Partial YAML edits empty the model list.** Deleting only a `modelID` line left `模型适配器 modelID 不能为空` and `agent --list-models` at 0 models. Restore from `config.yaml.bak3-20261023-0046` (or the newest pre-edit bak) and confirm channel count, not a hash alone: the app can rewrite the file (mtime/hash change) while length stays 12978 and 15 channels remain.

## Verification

`Import-Csv D:\cf\cursor-byok\nvidia_speed.csv` reports the expected total, and every row you call usable has `success` equal to `True` with a non-zero `ttft_ms` that came from body `content`. A model you still recommend after a `False`/timeout row must have a separate direct completion, not just a catalog id. `agent --list-models` is unchanged unless the user applied a config edit themselves.
