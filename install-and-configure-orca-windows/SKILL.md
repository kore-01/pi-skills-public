---
name: install-and-configure-orca-windows
description: Use when installing Orca on Windows, registering a workspace, or recovering a runtime lost after startup.
tags: ["自习"]
---

# Install and configure Orca on Windows

Install Orca, create a Git-backed workspace, register it through the bundled CLI, and verify persistence. This covers Windows installation and runtime setup; it does not configure model accounts or launch coding agents.

## When to Use
- The user says "安装 Orca" or "set Orca workspace to D:\ai\..." .
- Orca reports `runtime_unavailable`, `stale_bootstrap`, or exits after startup.
- You need to add an existing folder as an Orca project.

Don't use for:
- Choosing or authenticating an agent account.
- Launching a coding agent or provisioning a remote server.
- Editing Orca's SQLite profile database directly.

## Procedure
1. Check the workspace before modifying it. Confirm the target directory exists and whether it already contains files or `.git`; initialize a Git repository if Orca requires a worktree.

2. Try the package manager when the download host is reachable:

   `winget install --id StablyAI.Orca --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity`

   If the local GitHub route fails with `InternetOpenUrl() failed. 0x80072efd`, download the exact release URL on a reachable server, verify its SHA256 locally and remotely, transfer it with `scp`, then install it.

3. Install silently for the current user with:

   `Start-Process -FilePath $exe -ArgumentList '/S','/currentuser' -Wait -PassThru`

   Verify exit code `0`, the installed version, and `Orca.exe` under `%LOCALAPPDATA%\Programs\orca`.

4. Start the desktop app in the interactive Windows session, not directly from a disposable noninteractive shell:

   `Start-Process explorer.exe -ArgumentList "\"$exe\""`

   This avoids GUI processes being reclaimed when the shell session ends. `orca open` is blocking, so do not run it synchronously.

5. Add the folder through the bundled CLI:

   `& $cli repo add --path 'D:\ai\Orca' --json`

   Do not hand-edit `profile-state.db`, its WAL, or runtime credentials.

6. Check readiness before querying or registering:

   `& $cli status`

   Require `appRunning: true`, `runtimeState: ready`, `runtimeReachable: true`, `runtimeConnectionState: connected`, and `graphState: ready`. Then verify:

   `& $cli repo list --json`
   `& $cli worktree list --json`
   `& $cli project list --json`

   The project path must match the requested folder, `kind` should be `git`, and the worktree must show the expected branch.

7. Test persistence by gracefully closing Orca, stopping it if it does not exit promptly, restarting it through Explorer, and rerunning the CLI list commands. A SQLite WAL may contain the active profile state while the app is running; after restart, confirm the project remains listed rather than assuming WAL presence means failure.

## Pitfalls
- `appRunning: true` or `runtimeReachable: true` can briefly precede `graphState: unavailable`; wait and require the full readiness set before registering the workspace.
- `runtime_unavailable` often means the GUI was launched from a shell session that is later reaped. Use Explorer to launch it in the desktop session.
- A folder that is not a Git repository may produce `fatal: not a git repository`; initialize Git before relying on Orca worktree workflows.
- Do not add a duplicate SSH host if an existing alias already works. Reuse the tested alias and verify key authentication with `ssh -o BatchMode=yes`.
- A successful installer exit does not prove workspace configuration; verify the project and worktree through the CLI after restart.

## Verification
After restart, `orca status` reports `runtimeState: ready` and `graphState: ready`, and `orca repo list --json` contains the exact workspace path with `kind: git`; `orca worktree list --json` also contains that path and branch.
