---
name: windows-csc-self-extracting-installer
description: Use when a Windows exe installer is needed and NSIS/Inno are absent, or IExpress /Q builds no exe.
tags: ["自习"]
---

# Windows csc self-extracting installer

Build a double-click Windows setup exe by compiling a small C# extractor with the .NET Framework `csc.exe` and embedding `payload.zip` as a managed resource. This does not package an upstream closed binary, and it does not treat IExpress quiet mode as a working installer toolchain.

## When to Use

- Need `*-setup.exe` that extracts to `%LocalAppData%\...` and registers an HKCU Apps & Features uninstall key.
- `C:\Windows\System32\iexpress.exe /N /Q <sed>` exits 1 with empty stderr, or exits 0 but no exe appears.
- MakeCab report from the generated `~*.DDF` says `Total files: 0`.
- `csc.exe` exists at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`.

Don't use for:
- Machines without .NET Framework 4.x (`Framework64\v4.0.30319` missing).
- Editing an already-working SED by hand when a GUI IExpress wizard already produced the exe.
- Assuming `node --check` or prettier success means the installer ran.

## Procedure

1. Confirm the compiler and zip assemblies, not just that Windows is installed:

   `Test-Path "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"`

   `Get-ChildItem "C:\Windows\Microsoft.NET\Framework64\v4.0.30319" -Filter "System.IO.Compression*.dll"`

   Expect `csc.exe`, `System.IO.Compression.dll`, `System.IO.Compression.FileSystem.dll`, and `System.IO.Compression.ZipFile.dll`.

2. If diagnosing IExpress first, a minimal SED under `C:\ego-inst-test` still failed here. `iexpress /N /Q test.sed` left `~hello.DDF` and no `hello.exe`. Manual `makecab /f ~hello.DDF` printed `Total files: 0` / `Bytes before: 0`. Stop iterating SED key order (`FILE0=` vs `%FILE0%=`, `AdminQuietInstCmd`, `CabFileVersioning`) once the DDF has zero file entries. Switch to csc.

3. Script layout: the packager lives in `scripts/`, so package root is one parent, not two.

   `const packageRoot = join(dirname(fileURLToPath(import.meta.url)), "..");`

   Two `".."` segments produced `ENOENT` opening `D:\ai\ego\package\package.json`. Import `dirname` from `node:path` (`import { dirname, join, resolve } from "node:path";`) and `cp` from `node:fs/promises`.

4. Assemble a payload directory that already contains `install.cmd` and `uninstall.cmd`, then zip that directory. Zipping only `artifacts/windows-x64` left the extractor temp dir without `install.cmd` (`系统找不到指定的文件。`). Copy with `cp(..., { recursive: true })`, write the cmd files into `payloadSrc`, then:

   `Compress-Archive -Path (Join-Path $env:EGO_PAYLOAD '*') -DestinationPath $env:EGO_PAYLOAD_OUT -CompressionLevel Optimal -Force`

   Pass env from `spawnSync` as `{ EGO_PAYLOAD: payloadSrc, EGO_PAYLOAD_OUT: payloadZip }`. Inside PowerShell the names are `$env:EGO_PAYLOAD` and `$env:EGO_PAYLOAD_OUT`. `$EGO_PAYLOAD_OUT` makes DestinationPath null: `Cannot validate argument on parameter 'DestinationPath'. The argument is null or empty.`

5. Compile without shell quotes. `spawnSync` does not need quotes; literal quotes become the filename and csc reports `error CS2001` for `/out:...` and `/res:...,EGO_PAYLOAD`. Working argv:

   `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:exe /platform:anycpu /optimize+ /out:<outExe> /res:<payloadZip>,EGO_PAYLOAD /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll <staging>\extractor.cs`

   Delete an existing `outExe` before compile. Success log shape: `windows installer written to D:\ai\ego\package\ego-browser\artifacts\ego-browser-v0.1.0-windows-x64-setup.exe (291 KB)`.

6. Installer contract used here: extract embedded zip to `%LocalAppData%\ego-browser-runtime`, write `uninstall.cmd`, set `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ego-browser-runtime` with `DisplayName`, `DisplayVersion`, `Publisher`, `InstallLocation`, `UninstallString`, `NoModify=1`, `NoRepair=1`. Uninstall spawns a detached PowerShell (`Start-Sleep -Milliseconds 400`) because Apps & Features deletes `uninstall.cmd` while it is running.

7. If surgical edits corrupt the generator (duplicate `run()`, SED lines spliced into the `iexpress` join, `unusable_*` sentinels), stop patching and rewrite the whole `.mjs` with write. Then `node --check` and `npx prettier --write`.

## Pitfalls

- **IExpress exit 0 is not an exe.** Poll for the exe/CAB; `~hello.DDF` alone is a failed cabinet. `cv_debug.log` in `%TEMP%` was unrelated Edge telemetry.
- **`/Q` hides the real error.** Empty stderr plus exit 1 still means the SED never fed files to makecab.
- **Quoted csc args via spawnSync.** CS2001 naming `/out:...` means the quotes were passed as characters. Paths here had no spaces.
- **`$env:` vs `$.`** Compress-Archive only sees process env through `$env:`.
- **Payload zip missing the installer scripts.** Extraction can succeed into `%TEMP%\ego-browser-setup-*` while `Test-Path ...\install.cmd` is false.
- **PowerShell `2>&1` on the exe.** `无法处理来自 ... 的"Error"流的 XML` / `CliXmlError` is PS 5.1 wrapping stderr. Trust `installer_exit=0` and the files on disk.
- **Prettier/syntax is not install verification.** `syntax=0` happened before csc and before a real install.

## Verification

After running the setup exe, `%LocalAppData%\ego-browser-runtime` contains `runtime`, `ego-browser-local.cmd`, and `uninstall.cmd`; `Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ego-browser-runtime` shows `DisplayVersion : 0.1.0` and a quoted `UninstallString`. Runtime smoke from that install returns `{"ok":true,"taskSpace":"function","help":"function"}`. After `uninstall.cmd` and `Start-Sleep -Seconds 2`, both the directory and the HKCU key are gone (`Test-Path` false).
