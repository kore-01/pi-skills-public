# Checkpoint: 把 pi-skills 迁到 Kelivo 手机沙盒

## 目标
让 31 个技能能在 Kelivo 的 Linux 沙盒里被识别并可用；完成标准：`hermes skills list`（或 Kelivo 技能页）能看到 `time` 与 `kpl-stock-data`。

## 已完成
- ✅ 确认 Kelivo 手机版 = Android PRoot 沙盒，`/skills` 是 bind mount（`workspace_paths.dart` → `guestSkills = '/skills'`）
- ✅ 读 `skills_service.dart`，确认三种导入源：paste / file(.md|.zip) / github
- ✅ 实测 `codeload.github.com` 不带认证对私库返回 404 → 方案改为建公共镜像仓库 `kore-01/pi-skills-public`
- ✅ 用 GitHub MCP `push_files` 批量写入 `time/scripts/now.py` 与 `time/scripts/calendar.py`，blob SHA 与私库一致（`f1060168…` / `f57a0e10…`）
- ✅ 端到端验证：`https://codeload.github.com/kore-01/pi-skills-public/zip/refs/heads/main` 能取到含 `time/scripts/*` 的 ZIP

## 下一步
1. 剩余带 references/scripts 的技能补齐（`tavily/scripts/*`、`ego-browser/references/*`、`kpl-stock-data/scripts/kpls/*`）
2. 在 Kelivo「技能」页用「从 GitHub 导入」填 `https://github.com/kore-01/pi-skills-public/tree/main/time`
3. 导入后回读 `/skills/time/SKILL.md`，确认 frontmatter 的 name/description 都能解析

## 关键决策
- 决策 A：不做「粘贴 SKILL.md」方案，因为 `importFromText` 只接受单个文件、没有 frontmatter 校验，且手机端粘贴 30 个长文档不现实；GitHub 导入能带上 scripts/references 一起装。
- 决策 B：建公共镜像而不是给私库加 token —— Kelivo 的 `_githubHeaders` 是硬编码的 `User-Agent: Kelivo` + `Accept: application/vnd.github+json`，**不带 Authorization**，所以私库必然 404；公共仓库是唯一不改源码就能通的路径。
- 决策 C：`全面分析` 的 name 从 `KPL Finance Bundle (全面分析)` 改成 `kpl-finance-bundle`，因为 `slugify` 只保留 `[a-z0-9-]`，含空格和中文括号的 name 会 slugify 成空串后回退到 `skill`，多个技能会互相覆盖。

## 卡点
- 阻塞点 1：Kelivo 的 `importFromGitHub` 下载整个仓库 ZIP（16 MB），而 `_narrowToSkillRoot` 只在 `subdir` 指定时才会裁剪到目标技能。需要确认 URL 用 `tree/main/<subdir>` 形式时 `GitHubSkillRef.parse` 能正确取出 subdir。现象：导入时看到 `pi-skills-public-main/` 顶层目录。已试过：读 `github_skill_ref.dart` 确认 `tree` 形态会解析 `rest` 为 subdir。

## 重要上下文
- **路径**：`/skills/<name>/SKILL.md`（Kelivo 技能根，沙盒内只读）
- **命令**：`https://github.com/kore-01/pi-skills-public/tree/main/<skill-name>`（导入 URL）
- **约束**：仓库 `pi-skills-public` 必须保持 public；任何真实凭据不得入库
- **凭据位置**：`~/.hermes/credentials/tavily-keys.txt`（269 个 key，只在原机）
