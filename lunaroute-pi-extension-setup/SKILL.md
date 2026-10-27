---
name: lunaroute-pi-extension-setup
description: lunaroute models missing in pi /model after setup pi — D:\PI\pi.exe shadows npm pi, extension install silently skipped
tags: ["自习"]
---

# LunaRoute pi 扩展安装（修「模型找不到」）

让 `lunaroute/*` 模型出现在 pi（PI-Desktop）的 `/model` 列表里。pi 本体**没有任何 lunaroute 内置支持**——模型全靠 `@lunaroute/pi-extension` 扩展在启动时从 `https://gw.lunaroute.com/v1/models` 拉取注册。auth.json 里存了密钥≠模型会出现。

## When to Use

- 运行 `npx @lunaroute/cli setup pi --key lr_... --yes` 后，pi 里 `/model` 找不到 lunaroute 模型
- setup 输出了 `Done. Start pi — it is signed in` 但模型列表为空
- 任何「第三方 setup CLI 报成功，但目标程序里什么都没发生」的假成功场景

Don't use for: lunaroute 账户/余额问题（那是 `lunaroute whoami` / `usage` 的事）；其他 harness（opencode/claude-code 等）的配置。

## Procedure

1. **确认扩展是否真的装了**（假成功诊断）：

```powershell
& 'C:\Users\Administrator\AppData\Roaming\npm\pi.cmd' list
```

输出 `No packages installed.` = 扩展没装上。再看挡路者：`where.exe pi`——PATH 第一个是 `D:\PI\pi.exe`（PI-Desktop 图形程序），它不认识 `install` 参数却 exit 0，`@lunaroute/cli` 的 `spawn("pi", ["install", ...])` 被它吞掉。

2. **用完整路径的 pi 手动装扩展**（绕过 PATH shadowing）：

```powershell
& 'C:\Users\Administrator\AppData\Roaming\npm\pi.cmd' install npm:@lunaroute/pi-extension
```

装到 `~/.pi/agent/npm/node_modules/@lunaroute/pi-extension`，并写入 `~/.pi/agent/settings.json` 的 `"packages"`。

3. **验证密钥走的是网关而非账户 API**：

```powershell
node -e "fetch('https://gw.lunaroute.com/v1/models',{headers:{Authorization:'Bearer <lr_密钥>'}}).then(async r=>{console.log('status',r.status);const j=await r.json();console.log((j.data||[]).map(m=>m.id).join(', '))})"
```

4. **完全退出 PI-Desktop（含托盘）再重启**，`/model` 选 `lunaroute/*` 模型。扩展直接读 `~/.pi/agent/auth.json` 里 `{type:"oauth", access:"lr_..."}` 凭据，无需再 `/login lunaroute`。

## Pitfalls

- **假成功是主坑**：`setup pi --key --yes` 的 `installPiPackages` 只看 exit code。`D:\PI\pi.exe` 对未知子命令 exit 0，CLI 就继续写 auth.json 并打印 `Done. ... signed in`——用户以为一切正常，唯独模型永远不出现。验证任何 setup 是否真生效，要看产物（`pi list` / settings.json），不看 CLI 的话术。
- **401 陷阱**：`api.lunaroute.com` 是账户 API（whoami/login 用），拿 `Bearer lr_...` 打它的 `/v1/models` 必 401 `Invalid or expired token`。聊天流量和模型目录走 `gw.lunaroute.com`。别把 401 误判成密钥失效。
- pi 无头模式测试也要用完整路径 `pi.cmd`，直接 `pi` 会撞上 `D:\PI\pi.exe`。
- 可见聊天模型（2026-10 目录）：`beam`、`clef-flash`、`deepseek-4.1-flash`、`djev`、`glm-5.3`、`glm-5.3-flash`、`glm-5.3-vision`、`muse-spark-open`（`-background` 后缀为后台变体）；`whisper-large-v3` 是音频模型，扩展会过滤，聊天列表里没有是正常的。

## Verification

```powershell
& 'C:\Users\Administrator\AppData\Roaming\npm\pi.cmd' list          # 应列出 npm:@lunaroute/pi-extension
```
