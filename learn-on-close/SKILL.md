---
name: learn-on-close
description: Save finished work as a skill via skill_manage. Use after 3+ tool calls, a recovered mistake, or a correction. 记下来。
tags: ["自习"]
---

# Learn on close

The plugin `cn.star.skill-learning` runs a background review only when a turn
reaches five tool calls. That threshold misses the most valuable cases: a
two-call fix that took three wrong guesses first, and any task the user had to
steer. Those are exactly the lessons worth keeping, so this skill covers them at
close of task instead of relying on the threshold.

## When to Use

Ask at the end of a task, not during it. Write a skill if any of these is true:

- **Three or more tool calls** to reach the answer, and the path was not obvious
- **A mistake happened and was recovered from** — the wrong turn is the whole
  value, because the next session would take it again
- **The user corrected you** — "不对", "应该是…", "别这样". Their correction is a
  fact about the environment you could not have derived
- **An environment quirk was discovered** — a command that needs a specific
  shell, a path that must not be rewritten, a tool that reports success while
  doing nothing

Do not write a skill for:

- One-off Q&A with no procedure ("what does this flag do")
- An unresolved failure — a skill that says "this is broken" teaches nothing
- Anything already covered by an existing skill. Patch that one instead.
- Session-specific facts (a hostname, a token, a ticket number)

## Procedure

1. **Check what exists first.** Read the skill root before naming anything, so a
   near-duplicate does not get created:

   ```
   ls ~/.agents/skills
   ```

   If a skill already covers the area, patch it. `skill_manage` enforces
   read-before-write, so read its `SKILL.md` first.

2. **Name it for the class, not the incident.** `deploy-worker-custom-domain`,
   not `fix-k3-eatea-404`. The quality gate rejects names matching
   `^(fix|debug|audit|hotfix)-`, ending in three or more digits, or containing
   `pr-123`.

3. **Write the full document** through `skill_manage`:

   ```json
   {
     "action": "create",
     "name": "deploy-worker-custom-domain",
     "content": "---\nname: deploy-worker-custom-domain\ndescription: …\n---\n\n# …\n"
   }
   ```

4. **Put the command that actually worked in the procedure, verbatim.** A
   paraphrase loses the argument that made it work — the `--noproxy '*'`, the
   `-x` proxy flag, the quoting. Copy it from the session.

5. **Long detail goes to `references/`.** Keep `SKILL.md` under 500 lines and
   under 80 KB; the gate warns past 80 KB and the loader refuses past 128 KB.
   Use `action: "write_file"` with `file_path: "references/<topic>.md"`.

6. **When patching, replace a unique substring** with `action: "patch"`,
   `old_string`, `new_string`. Read the file first. Never rewrite a whole skill
   to change one line.

## Writing what the gate requires

The validator rejects a document without these sections. They are not
decoration: they are the two things a future session needs and a summary omits.

```markdown
---
name: example-name
description: One sentence, under 120 characters, saying when to use it.
---

# Title

What it does, and what it deliberately does not.

## When to Use
- Concrete triggers, phrased as the user would say them.

Don't use for: …

## Procedure
1. The exact command, copied from the session.
2. …

## Pitfalls
- The thing that looked like success but was not.

## Verification
One check that proves it worked.
```

The `description` is the only field the catalog shows, so it must carry the
trigger words. `## Pitfalls` and `## Verification` are mandatory; Chinese
headings `## 陷阱` / `## 验证` are accepted too.

## Pitfalls

- **Writing during the task.** The procedure is not settled until the task ends;
  an early draft records the wrong approach. Write at close.
- **Recording the fix, not the trap.** "Use `--noproxy '*'`" is weak.
  "PI-Desktop hands curl a loopback relay, so a TUN proxy needs Direct mode"
  explains why, and survives a different symptom.
- **Duplicating a skill that already exists.** Two near-identical skills both
  lose ranking. Check first, patch second.
- **A description with no trigger words.** "Helps with Cloudflare" never fires.
  "Use when binding a custom domain to a Worker or Pages project" does.
- **Ten-line recaps.** If the Procedure has fewer than three steps, it is not a
  procedure — it is a note, and belongs in the existing skill's Pitfalls.

## Cross-cutting traps worth saving (PI-Desktop environment)

These keep biting across unrelated tasks. If a future session hits a symptom
from this list, the fix is already known — patch an existing skill or note
it, do not re-debug.

- **`pi edit` corrupts `r"""` docstrings.** When the procedure column contains
  `r"""..."""`, the edit tool escapes it to `r\"\"\"...\"\"\"` (literal
  backslashes). Python then raises
  `SyntaxError: unexpected character after line continuation character` at
  the `r"""` line. Symptom: file parses fine elsewhere but python raises the
  error at the first triple-quoted string. Fix: rewrite the whole affected
  section by overwriting via `pi write`, do not try to surgically patch the
  `r"""` opener.
- **New public JSON routes need TWO fixes, not one.** Adding a path like
  `/foo/_data.json` requires (a) nginx `location ^~ /foo/_data` proxy block
  and (b) a whitelist entry in `path_needs_auth()` *before* any
  `path.endswith(".json")` check. Without the backend whitelist, nginx
  forwards the request, auth_gate returns 401, and the debug message
  ("请先登录 Kore 账号") makes it look like a missing nginx route when the
  route is actually present. Verify with `curl -sS -o /dev/null -w '%{http_code}'`
  *both* at 127.0.0.1 and through the public domain.
- **`pi bash -c "<inline python>"` fails on PowerShell** when the script has
  nested `"` or Chinese characters (`只应将 ScriptBlock 指定为 Command 参数值`).
  Workaround: write the inline script to a file with `pi write` then run it
  with `pi bash` referencing the file. The file path survives quoting intact.
- **`urllib` can spend 5–6 seconds on unreachable IPv6 while `curl` hides the
  problem.** If a Python `urllib.request.urlopen` upstream fetch takes 7–9
  seconds, but same-host `curl -4` takes about 2–4 seconds and `curl -6` fails,
  inspect DNS and outbound IPv6 rather than blaming concurrency or the
  browser. In `serve.py`, add `import socket`, wrap the original resolver,
  reorder results with `AF_INET` before other families while retaining IPv6 as
  fallback, and assign `socket.getaddrinfo = _v4_first_getaddrinfo`. Back up each
  file, run `python3 -m py_compile`, restart `kpl-raw`, and verify the service is
  `active`, the page returns `200`, and repeated `/api/wenap/auction` requests
  fall from `6.45~9.45s` to roughly `1.92~3.58s`.
- **A failed MySQL unit does not prove MySQL is down; inspect process cgroups
  before editing units.** If `mysqld.service` reports failed while MySQL is still
  serving, check the live process's `/proc/<pid>/cgroup` and identify the actual
  unit. A custom `mysql8046.service` may own the process while the generated
  SysV `mysqld.service` collides on the same datadir/socket. Confirm `MainPID=0`
  for the failed unit, inspect every related unit's `enabled`/`active` state, and
  distinguish `After=` from `Wants=` or `Requires=` before masking anything.
- **Sort keys that can tie will diverge across machines.** When
  `_items.sort(key=lambda r: -r["probability"])` is the only key and two rows
  tie (e.g. `probability == 82` for both `002164` and `603859`), Python's sort is
  stable but the input order varies, so `55`/`212` pick one and `220` picks the
  other. Three-machine results silently drift apart. Always add a deterministic
  secondary key before data is kept:
  `_t.sort(key=lambda r: (-_prob_key(r), str(r.get("code") or "")))`. Verify by
  running the same endpoint on all three boxes and comparing the comma-joined
  codes (`001323,605488,002164`) before declaring done.
- **Reuse the shared renderer, or you will re-derive every cross-cutting
  feature (e.g. 通达信/treeid 跳转).** `renderWatchRow()` in `智核一和二竞价.html`
  already emits `onclick="window.open('http://www.treeid/code_' + code,'_self')"`
  plus `<a class="wr-code stock-tdx">` + `event.stopPropagation()`. Any pool that
  bypasses it will silently lose the jump-to-tdx behavior. Verify by
  `grep -n 'stock-tdx' <new-renderer-file>` AND a live click in the browser, not
  just by code review.
- **A standby host must use an explicit pull-only sync mode; never schedule a
  default `both` rsync.** A healthy TCP/SSH connection does not make bidi
  `--update` safe: the standby can push a newer local file into production. Add a
  `--pull-only` branch that calls only the peer-to-local function, retain
  warnings for `both`, and test that the output contains the pull banner but zero
  push actions. A useful acceptance output is `安全模式：单向拉取 212 -> 55（不推送）`
  with `推送` occurrence count `0`; also exercise `flock` and run a dry-run under
  `env -i` before installing cron.
- **CRLF → LF pollution makes git diff balloon 5-10x after Python script
  rewrites.** When a sed-style Python replace script touches a file on Linux that
  was originally CRLF-terminated, the rewrite silently strips `\r\n` to `\n`,
  and git reports every line as changed. Fix recipe used and verified: (1)
  detect with `python -c "d=open(f,'rb').read(); print(d.count(b'\\r\\n'), d.count(b'\\n'))"`
  per file; (2) re-inject CRLF by writing in binary —
  `open(f, 'wb').write(content.replace(b'\\n', b'\\r\\n'))`. Caveat: only
  re-inject where the **original file on the source machine was CRLF**. The
  correct decision rule: **do not chase byte-perfect diff; transfer files as
  binary SFTP** (`sftp.put(local, remote)` with no text-mode transforms) and
  ignore the diff noise in any patch. Verify with `git diff --shortstat -w` for
  the ground-truth change size.
- **With `set -uo pipefail`, `zcat "$F" | grep -q ...` can falsely report a
  missing table.** `grep -q` exits immediately on a match, causing `zcat` to
  receive SIGPIPE; `PIPESTATUS` then makes a healthy dump look invalid. If an
  audit shows the key table exists and `grep -c` finds it, decompress to a
  temporary file first, then grep that file. Verify the artifact with `gzip -t`,
  the `CREATE TABLE` count, required table names, and the dump completion marker.
- **On Ubuntu, `/var/log` being group-writable makes logrotate reject every log
  beneath it.** The exact error is `skipping "..." because parent directory has
  insecure permissions`. Check with `stat -c '%A %U:%G %n' /var/log`; the safe
  state is `drwxr-xr-x root:syslog`, so use `chmod 755 /var/log`. If logs are
  large, also cap systemd with `SystemMaxUse=200M` and
  `SystemMaxFileSize=50M`, run `journalctl --vacuum-size=200M`, and use
  `logrotate -d` before relying on new cron-log policies.
- **`opencode web` only honours `--port=N` / `--hostname=N` when written with
  `=`; the space form silently falls back to defaults.** Symptom: a unit file
  with `ExecStart=... opencode web --port 4096 --hostname 0.0.0.0` looks like it
  works (because the default port happens to be 4096), but switching to `--port
  8080 --hostname 127.0.0.1` leaves port 8080 unbound — the daemon is still
  listening on 4096. There is no parse error; the args are simply not parsed.
  Fix: always write `ExecStart=... opencode web --port=8080 --hostname=127.0.0.1`
  with `=`. Verify with `ss -tlnp | grep ':8080'` after `systemctl restart`, never
  trust the unit file's text alone.
- **A missing cron logfile may mean the production window was missed, not that
  cron or the script is broken.** Before rerunning market-data collectors after
  hours, compare daemon state, the exact crontab schedule, syslog execution
  records, output timestamps, and script checksums across hosts. If a probe proves
  `env -i /usr/bin/python3 /opt/chyl2/l2_precompute.py --help` exits 0 but the
  crontab was installed after the scheduled window, do not manually backfill or
  mark `--final`; let the next trading-day window populate the baseline. Verify
  after 09:40 with `/root/verify_nextday.sh`, `/opt/chyl2/log.txt`, and the final
  item count.

## Verification

After installation, read back SKILL.md and its referenced files. Link the saved
entrypoint as `kelivo://skills/<skill-directory>/SKILL.md`, using the actual
directory name and URI-encoding each path component. Claim installation only
after saving and verification succeed. New skills are enabled by default; an
assistant or conversation with an explicit skill selection may need the new
skill selected.
