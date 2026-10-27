---
name: inspect-orca-live-agents
description: Use when checking how many Orca agents are live in a worktree after agent list fails.
tags: ["自习"]
---

# Inspect live Orca agents

List agents actually running inside one Orca worktree by reading `orca worktree ps` and `orca terminal list`/`read`. This does not launch, steer, or stop agents, and it does not treat a worktree count of 1 as proof only one agent is running.

## When to Use

- User asks whether several AIs are tracking the same task at once.
- `orca agent list` printed `Unknown command: agent list` and exited 1.
- Need each agent's type, prompt, state, terminal handle, and last output.

Don't use for:
- Installing Orca, registering a workspace, or starting a remote PI agent.
- Full handoff (`worktree create --agent`, `agent launch`, `terminal send`).
- Treating `hostScope.hostIds: ["local"]` as the full fleet when `omittedHostSelectors` names another environment.

## Procedure

1. Resolve the CLI the way the session already did: bare `orca` on this Windows host (version printed `1.4.237`). Do not invent `orca-dev` unless `ORCA_DEV_REPO_ROOT` is set. If a command says Orca is not running, `orca open --json` then retry. On `runtime_access_denied`, re-run escalated; do not `orca open`.

2. Load the version-matched guide before guessing subcommands:

   `orca skills get orca-cli`

   `orca agent list` is not a command (`Unknown command: agent list`, exit 1).

3. List worktrees, then the process view that actually embeds agents:

   `orca worktree list --json`

   `orca worktree ps --json`

   Copy the full id (`70bce211-e133-4121-a78a-bd0045cd00f1::D:/cf` here). A bare repo id is not a worktree id. Read `result.worktrees[].agents[]` (`agentType`, `state`, `prompt`, `paneKey`, `lastAssistantMessage`) and `liveTerminalCount`. This session: `totalCount` 1 worktree, `liveTerminalCount` 3, agents `cursor`/`pi`/`opencode`.

4. If `hostScope.omittedHostIds` is non-empty, say so. Observed omission: `runtime:1fda7660-7856-4d1f-b84b-4b6192236a87` with selector `--environment srv168`. Local commands do not cover that host.

5. Map panes to terminals:

   `orca terminal list --worktree id:70bce211-e133-4121-a78a-bd0045cd00f1::D:/cf --json`

   Match `leafId` to the agent `paneKey` suffix. Require `connected: true`. Handles seen: `term_0aa1446d-d2d3-4c3a-8061-23bdc70104ef` (opencode), `term_227506c8-995e-47da-b633-2372dbd2b043` (pi), `term_43ae4a06-a3c0-4483-8dc2-772b48be3662` (cursor).

6. Read tails without sending input:

   `orca terminal read --terminal term_0aa1446d-d2d3-4c3a-8061-23bdc70104ef --limit 60 --json`

   Repeat per handle. `result.terminal.status` of `running` plus `ok: true` is the live signal. In PowerShell, `Select-Object -First 60` can set the tool `exitCode` to -1 while the JSON body is still `ok: true`; judge the JSON, not that wrapper code.

7. Report type, title, state, and the concrete next action from the tail. Do not merge their conclusions into a new deploy or a forced poll.

## Pitfalls

- **`worktree list` totalCount hides extra agents.** One worktree with `liveTerminalCount: 3` is three agents in one tab, not one agent.
- **`agent list` failure is a bad subcommand, not a dead runtime.** `orca --version` already exited 0.
- **Local JSON omits paired runtimes.** `omittedHostSelectors` / `--environment srv168` means those agents were not inspected.
- **PowerShell truncation looks like a failed read.** `exitCode: -1` with `stdout` containing `"ok": true` and a `tail` array is a truncated success.
- **`state: done` on one agent is not "all stopped".** opencode was `done` while pi and cursor stayed `working` and terminals stayed `connected: true`.
- **Preview text is not the report.** `worktree ps` `preview` and terminal `preview` can be a spinner (`pipi login` / `Working`); use `terminal read` tails before summarizing progress.

## Verification

`orca worktree ps --json` is `ok: true`, and the number of `agents` entries equals `orca terminal list --json` `totalCount` for that worktree id (3 and 3 in this session), each with `connected: true`. Every claimed activity is backed by a `terminal read` tail, not by `liveTerminalCount` alone.
