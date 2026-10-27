---
name: verify-ego-browser-fingerprint
description: Use when checking ego-browser applyFingerprint on whoer or CreepJS through the ego lite CLI.
tags: ["自习"]
---

# Verify ego-browser fingerprint

Smoke-test `page.applyFingerprint` by piping a JS script into ego lite's `ego-browser.exe nodejs` and reading the page's navigator identity. This does not change fingerprint presets, and it does not treat a screenshot return string as a saved file.

## When to Use

- User asks to test fingerprint effect now that a normal display / pixel readback is available.
- Need to confirm `applyFingerprint("us")` landed timezone, locale, geolocation, and extra HTTP headers.
- whoer.net or creepjs.com should show a US desktop identity (en-US, America/New_York, webdriver false).

Don't use for:
- Editing preset definitions or the UA-gate snap from major 154 to 152.
- Proving a site's TLS stack; `net::ERR_SSL_VERSION_OR_CIPHER_MISMATCH` is a navigation failure, not a fingerprint miss.
- Hosts where `C:\Program Files\Citro Labs\ego lite\Application\0.6.0.16\ego-browser.exe` or `D:\ai\ego\package\ego-browser\dist\out\index.js` is missing.

## Procedure

1. Confirm the binary and the locally built SDK, not just that ego processes exist:

   `Test-Path "C:\Program Files\Citro Labs\ego lite\Application\0.6.0.16\ego-browser.exe"`

   `Test-Path "D:\ai\ego\package\ego-browser\dist\out\index.js"`

   Both must be `True`. Do not use `Test-NetConnection` to probe whoer/creepjs; it hit the 15s bash budget with no result. Do not use PowerShell `curl --max-time` (`找不到接受实际参数“--max-time”的位置形式参数`) or `Invoke-WebRequest -TimeoutSeconds` (`找不到与参数名称“TimeoutSeconds”匹配的参数`). Drive the sites through the browser instead.

2. Scripts are stdin-only. Helpers (`taskSpace`, `fingerprintModes`, `page.applyFingerprint`, `page.goto`, `page.evaluate`) are injected globals. `ego-browser.exe` with extra argv prints usage and returns 2. Pipe a file:

   `Get-Content "D:\ai\ego\.pi-desktop\scratch\<id>\fingerprint-test.mjs" | & "C:\Program Files\Citro Labs\ego lite\Application\0.6.0.16\ego-browser.exe" nodejs --sdk-path "D:\ai\ego\package\ego-browser\dist\out\index.js"`

   Use a 120s tool timeout. The working script shape:

   `const task = await taskSpace("fp-test");`
   `const page = task.page("p1");`
   `const modes = await fingerprintModes();`
   `const receipt = await page.applyFingerprint("us");`
   `await page.goto("https://whoer.net", { waitUntil: "load", timeout: 30000 });`
   `await page.waitForTime...`
   `out(2000);`
   `const identity = await page.evaluate(() => ({ ua: navigator.userAgent, platform: navigator.platform, language: navigator.language, languages: navigator.languages.join(","), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory, screen: [screen.width, screen.height], colorDepth: screen.colorDepth, maxTouchPoints: navigator.maxTouchPoints, webdriver: navigator.webdriver, timezoneOffset: new Date().getTimezoneOffset() }));`

3. Require this receipt for mode `us` (log line may also say `[kore ua-gate] major 154 ahead of heuristic-safe cap 152 (kernel 153); snap → 152`):

   `receipt: {"mode":"us","timezone":"America/New_York","language":"en-US","failed":[],"applied":["Emulation.setTimezoneOverride","Emulation.setLocaleOverride","Emulation.setGeolocationOverride","Network.setExtraHTTPHeaders"],"injected":true}`

   Modes printed here: `auto: 自动`, `us: 美国站`, `jp: 日本站`, `eu: 欧洲站`.

4. Require the page identity (whoer https succeeded once; a later rerun died at `navigateInPage` with `ego's nodejs process exited with code 1` — retry once, do not change the preset):

   - `ua` contains `Chrome/154.0.0.0` (page UA stayed 154 even after the ua-gate snap log)
   - `platform` `Win32`, `language` `en-US`, `languages` `en-US,en`
   - `timezone` `America/New_York`, `timezoneOffset` `240`
   - `hardwareConcurrency` `8`, `deviceMemory` `8`, `screen` `[1920,1080]`, `colorDepth` `24`, `maxTouchPoints` `0`, `webdriver` `false`

5. CreepJS: `https://creepjs.com` failed with `page.goto failed: net::ERR_SSL_VERSION_OR_CIPHER_MISMATCH`. Retry `http://creepjs.com` with the same apply + evaluate. That run exited 0 and matched the whoer identity including `webdriver: false`.

6. If a handbook note is required, append under the runtime fingerprint manual's pitfalls, then commit only that file. Do not claim screenshots were archived unless `Test-Path` on the png is `True`.

## Pitfalls

- **Screenshot return string is not a file.** `page.screenshot` logged `screenshot saved: D:/ai/ego/.pi-desktop/scratch/fingerprint-whoer.png` and `screenshot: D:/ai/ego/.pi-desktop/scratch/fingerprint-creepjs-http.png`, but `Test-Path` on both was `False`. Only the `.mjs` files were in the scratch dir.
- **whoer success is not stable.** The first https load printed the full identity; the immediate rerun exited 1 during `page.goto` before identity. One failure after a pass is not a fingerprint regression.
- **CreepJS https cipher mismatch is not an identity failure.** Switch to `http://creepjs.com`. Do not debug Chromium TLS from this symptom.
- **UA-gate log vs page UA.** `snap → 152` in stderr while `navigator.userAgent` still says `Chrome/154.0.0.0` is the observed pair. Do not "fix" the page UA to 152.
- **Truncating CLI output hides the CDP tail.** `Select-Object -First 40` cut the run before `=== CDP navigator check ===` finished. Read the full stderr; the CLI writes the script log to stderr and leaves stdout empty.
- **PowerShell curl/IWR probes waste the timeout budget.** They are the wrong client on this host.

## Verification

The piped `ego-browser.exe nodejs --sdk-path ...` run exits 0, stderr contains `"failed":[]` and `"injected":true`, and `page.evaluate` JSON shows `America/New_York`, `en-US`, `webdriver` false, and `Chrome/154.0.0.0`. `http://creepjs.com` matches that identity. A png path in the log counts only after `Test-Path` is `True`.
