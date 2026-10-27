---
name: configure-orca-remote-pi-agent
description: Use when installing orca on a Linux SSH host, or making PI run remotely as an Orca agent.
tags: ["自习"]
---

# Configure Orca remote PI agent

Install and authenticate PI on a Linux Orca host, distinguish paired-runtime execution from SSH execution, and verify an agent launch. This does not add SSH targets or SSH-host project setups; Orca requires those through the desktop UI.

## When to Use
- The user says "在 Orca 服务器安装 pi", "让远端 Orca 跑 coding agent", or asks to verify an SSH coding host.
- `orca host list` shows a connected SSH target but its server lacks PI, credentials, or an agent runtime.
- `orca agent launch` returns `agent_launch_replay_unsupported` for a paired environment.

Don't use for:
- Installing Orca Desktop on Windows.
- Registering SSH targets or creating project setups on SSH hosts through the CLI.
- Editing `auth.json` secrets or printing credential values.

## Procedure
1. Confirm Orca readiness and host topology:

   `orca status`
   `orca host list --json`

   Require `runtimeState: ready`, `runtimeConnectionState: connected`, and `graphState: ready`. Record the target name, id, selector, and `connected` state.

2. Inspect the paired runtime before installing anything:

   `orca environment status --environment srv168 --json`
   `orca repo list --environment srv168 --json`

   A connected SSH target and a paired environment are distinct routes. The paired environment may expose `/root/.orca-remote` and a managed bare Node binary, but that binary may have no npm and its hashed path can change during updates.

3. Install stable system-level Node and PI on Ubuntu/Debian when durable host-level CLI availability is required:

   `curl -fsSL https://deb.nodesource.com/setup_24.x | bash -`
   `apt-get install -y nodejs`
   `npm install -g @earendil-works/pi-coding-agent`

   Verify with `node -v`, `npm -v`, `command -v pi`, and `pi --version`.

4. Seed an empty PI profile, then copy only required PI configuration over an authenticated SSH transport:

   `scp -o ConnectTimeout=20 "$env:USERPROFILE\.pi\agent\auth.json" root@HOST:/root/.pi/agent/auth.json`
   `scp -o ConnectTimeout=20 "$env:USERPROFILE\.pi\agent\settings.json" root@HOST:/root/.pi/agent/settings.json`

   Never print or copy session data, extensions, prompts, or unrelated model-store state by default. Set restrictive permissions on credential files.

5. Prove PI works independently of Orca before testing orchestration:

   `ssh srv168 'timeout 90 pi -p "只回复两个字：收到" --no-session < /dev/null'`

   Require the exact requested response; `No API key found for the selected model.` means installation succeeded but authentication did not. Use `pi auth check --provider <id> --json` for a faster readiness probe that avoids the TTY/stdin hang some SSH transports trigger.

6. For a paired runtime, use project target flags rather than combining repository selectors:

   `orca project list --environment srv168 --json`
   `orca project setups --environment srv168 --json`
   `orca worktree create --project PROJECT_ID --host runtime:ENVIRONMENT_ID --name remote-pi --agent pi --prompt "只回复这六个字：远程agent就绪" --json`

   Never pass `--repo` together with `--project/--host`; the error is `Choose either --repo or project target flags, not both.` Obtain `ENVIRONMENT_ID` from `orca environment list`, not the environment name.

7. Interpret replay failures by route. If a paired or SSH-remote CLI launch returns `agent_launch_replay_unsupported`, inspect `orca environment update --environment srv168 --json`. An `outcome` of `already-current` means changing the remote orcad component is not the correction; the launch protocol remains unsupported through that CLI route. Do not repeatedly retry or claim the CLI launch succeeded. Use the desktop UI to configure SSH-host project setups and launch the agent there.

8. When the CLI launch route is rejected but SSH remote execution is available, use the terminal API workaround instead of retrying `agent launch`:

   `$h = (& $cli terminal create --environment srv168 --worktree path:/tmp/orca-test --command "pi" --json | ConvertFrom-Json).result.terminal.handle`
   `& $cli terminal send --environment srv168 --terminal $h --text "只回复这六个字：远程agent就绪" --enter --wait-submit 20 --json`
   `& $cli terminal read --environment srv168 --terminal $h --screen --json`
   `& $cli terminal focus --environment srv168 --terminal $h --json`

   `terminal send` may return `observation: "unsupported"` while `input_accepted` is present and warning `input was accepted, but this provider cannot report delivery. Inspect the terminal before retrying.` Treat this as undetermined delivery: read the screen once, and do not resend blindly.

9. When a launch or terminal workaround succeeds, retain the returned handle and verify the rendered terminal:

   `orca terminal read --terminal HANDLE --screen --json`

   Require the requested response in `result.terminal.tail`, `status: running`, and `agentIdentity: pi` in `orca terminal list --json`.

## Pitfalls

- **A command named `pi` is not necessarily PI Coding Agent.** In PI-Desktop on Windows, `D:\PI\pi.exe` can precede `C:\Users\Administrator\AppData\Roaming\npm\pi.cmd` on `PATH`. A setup utility that spawns `pi install npm:@lunaroute/pi-extension` may receive exit code `0` from the desktop executable without installing anything, so credentials are written but `lunaroute/*` models never sync. Resolve the executable first with `Get-Command pi -All`; invoke the coding agent explicitly with `& 'C:\Users\Administrator\AppData\Roaming\npm\pi.cmd' install npm:@lunaroute/pi-extension`, then verify with `& 'C:\Users\Administrator\AppData\Roaming\npm\pi.cmd' list`. Require the extension to appear instead of merely requiring exit code `0`. Inside PI, `/login lunaroute` then syncs `/v1/models`; `/model` should list a `lunaroute/*` model.
- **PI itself has no LunaRoute provider merely because its package contains a string in source or a model-sync message.** The observed `@earendil-works/pi-coding-agent` package had zero matches for `lunaroute`; dynamic registration comes from `npm:@lunaroute/pi-extension`. A manual `providers.lunaroute` block in `~/.pi/agent/models.json` is a fallback, while the setup flow may remove that stale block after installing the extension because the extension syncs live.
- **A direct 401 from `https://api.lunaroute.com/v1/models` is a credential test, not proof that model sync is wired into PI.** LunaRoute uses `Authorization: Bearer lr_…`, but never print or embed the key in logs. A successful `@lunaroute/cli` models call does not prove PI's extension is installed; verify PI with its own `pi list` and `/model` output.
- `orca host list` showing a connected SSH target does not mean a remote repo is registered in the local runtime. Query scopes explicitly.
- `orca worktree list --json` may omit paired environments under `hostScope.omittedHostIds`; query with `--environment NAME --json`.
- The paired environment's `activeVersion: 0.1.0+...` is not comparable to the Desktop version. `environment update` returning `already-current` does not prove launch-replay compatibility.
- `outcome: already-current`, a running `orcad`, or a successful direct `pi -p` test does not prove Orca can launch PI remotely.
- Accumulated terminal output is unsuitable for TUI verification; use `--screen`. Draft composer text is not submitted output.
- Copying `auth.json` exposes credentials over the SSH connection and at rest. Never include its contents in logs or skill files.
- **A local repo with no remote cannot reach a paired runtime via `setup-clone`.** Bundle locally (`git bundle create <file> --all`), scp to the host, then `git clone --bare <bundle>` and `git clone <bare> <worktree-path>` there. The paired runtime treats the cloned path as a brand-new repo; the local repo id is *not* reused.
- **The paired runtime has its own projects database.** `orca account add --environment srv168` returns `invalid_argument`; account add never retargets across hosts. To seed a repo on the paired runtime, `orca repo add --environment srv168 --path /path/on/srv168` first; then `orca project setups --environment srv168` will show it.
- **PI on Debian 12+ / Ubuntu may hang silently without a stdin sink.** `pi -p "..." --no-session` over `ssh host 'cmd'` can produce zero output and exit 124. Symptom: `pi auth check --provider minimax-cn --json` returns `{"status":"ready"}` and yet `pi -p` times out. Root cause: the inherited SSH stdin keeps PI waiting for TTY input even with `--no-session`. Fix: redirect stdin from `/dev/null` (`ssh host 'pi -p "..." --no-session < /dev/null'`), or wrap with `</dev/null`. The provider readiness probe (`pi auth check`) is faster and avoids the hang — use it before running a full prompt.
- **OpenCode CLI on the host is NOT the agent.** `opencode` (e.g. 1.19.3) stores credentials in a SQLite DB (`~/.local/share/opencode/opencode.db`), has no `auth import` subcommand, and is not what Orca's `agent launch --agent pi` invokes. If `which codex` / `which claude` are absent and `which opencode` exists, do not be misled into copying credentials into `~/.local/share/opencode/` — install `pi` instead.
- **`orca worktree create --agent pi --model ...` rejects `--model` for PI.** Error: `Agent pi does not support launch-time model selection. Omit --model to run the model from its own config.` Selection happens via PI's own config / `~/.pi/agent/settings.json`, not via Orca at launch.
- **`orca account list --environment srv168` is unsupported even though `host list` shows a paired server.** Output: `--environment does not retarget 'orca account list'. Run it on the host whose accounts you want to manage.` Account state is per-Orca-runtime, not per-environment; the local list reflects only the local runtime. For remote runtimes the CLI exposes no account list — rely on `pi auth check --json` on the host instead.

## Verification
A completed setup requires direct `pi -p` output followed by a successful Orca launch whose terminal screen contains the expected reply and whose terminal list reports `agentIdentity: pi`. If the route returns `agent_launch_replay_unsupported`, the correct verification result is "PI installed and directly usable, Orca paired-runtime launch unsupported," not success.
