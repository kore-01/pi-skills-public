---
name: infinite-context
description: "让任意 agent/工作流获得「无限上下文」能力——外部持久记忆 + 自动检查点(checkpoint) + 上下文重建(resume)，突破固定窗口限制。对标小米 MiMo Code 记忆架构，通用自包含可发布。触发:无限上下文/infinite context/建检查点/记进度/接着干/恢复进度/checkpoint/resume/长任务不断档。"
agent_created: true
---

# Infinite Context（无限上下文 · 发布版）

## 这是什么
一套让 LLM agent **突破固定上下文窗口**的通用范式。不是真·扩大窗口，而是：

> 把记不住的东西搬出窗口、存到外部（文件/记忆），需要时再捡回来重建简报，接着干。

对标小米 MiMo Code 的「无限上下文」机制（外部持久记忆 + 检查点子代理重建），但做成**任何宿主都能直接用的独立 skill**。

## 为什么需要
| 场景 | 没有它 | 有它 |
|------|--------|------|
| 长周期编程 | 200 轮后失忆崩 | 检查点兜底，稳定续干 |
| 跨会话研究 | 重开从零讲 | 读 checkpoint 秒恢复 |
| 多 Agent 协作 | 各自健忘 | 共享同一份记忆 |
| 一次性短问答 | — | 不需要（开销无意义）|

## 快速开始
1. 长任务进行中，说「建检查点」或「记一下进度」
2. 按模板写入 `checkpoints/YYYY-MM-DD-HHmm.md`
3. 下次 / 新会话说「接着干」/「resume」
4. 读最新 checkpoint 生成简报，主 agent 无缝续干

## 关键概念
- **项目根目录**：从当前工作目录逐级向上，取第一个存在 `.workbuddy/memory/checkpoints/` 或 `checkpoints/` 的目录为项目根；上级都没有则用当前工作目录。
- **checkpoints 目录**：`<项目根>/checkpoints/`（WorkBuddy 可放 `<项目根>/.workbuddy/memory/checkpoints/`）。

## 执行步骤（操作手册 · 宿主无关）
### 建检查点
1. 取时间戳：
   - 优先用对话中宿主提供的时间（如 `<current_time>` 字段）
   - 否则用命令生成——
     - Git Bash / Linux / macOS：`date +%Y-%m-%d-%H%M`
     - PowerShell：`Get-Date -Format "yyyy-MM-dd-HHmm"`
2. 确定落盘目录，不存在则创建：
   - Git Bash / Linux / macOS：`mkdir -p <目录>`
   - PowerShell：`New-Item -ItemType Directory -Force -Path <目录>`
3. 用宿主提供的文件写入能力，将 `references/checkpoint-template.md` 模板按**当前任务真实填写**后写入 `<目录>/<时间戳>.md`：
   - WorkBuddy：Write 工具
   - 通用：文件系统 API / shell 重定向（`cat > file <<'EOF'` 或 `Set-Content`）
4. 回复用户：`已建检查点：<路径>`

### 重建（resume）
1. 定位项目根（见上「项目根目录」），**两个目录都列**：`<项目根>/.workbuddy/memory/checkpoints/*.md` 与 `<项目根>/checkpoints/*.md`，按文件名（时间戳）降序取最新
2. 读取该文件
3. 将其内容作为背景上下文纳入接下来的规划 / 回复，无需用户重复历史
4. 接着干，不从零开始；若开局检测到未完 checkpoint，主动询问是否恢复

### 收敛记忆（可选）
1. 读取全部 `checkpoints/*.md`，去重合并进长期记忆文件（如 MEMORY.md）
2. 清理过时项，避免记忆膨胀

## Checkpoint 内容
见 `references/checkpoint-template.md`：目标 / 已完成 / 下一步 / 关键决策 / 卡点 / 重要上下文（路径·命令·约束）

## 规则（硬）
- append-only，绝不覆盖旧 checkpoint（文件名带时间戳天然隔离）
- 不存明文密钥 / token
- 不编造进度、不虚构已完成步骤
- 与宿主安全 / 诚实规则冲突时让位

## 兼容性
- **已验证**：Windows（Git Bash + PowerShell 原生）、Linux（bash/POSIX 完整流程实测）
- **设计兼容**：macOS（同 BSD 工具链，`date` 格式兼容，理论可用但未独立实测）；任意支持文件读写的 agent 框架
- 唯一硬依赖：宿主能读写文件。无第三方库、无网络。

## 故障排查
- 目录不存在 → 先创建（见上）
- 路径含空格 / 中文 → 用引号包裹路径
- checkpoint 越积越多 → 定期执行「收敛记忆」
- 时间戳命令报错 → 直接用宿主对话中提供的时间，或人工指定

## 示例
见 `references/example.md`（一个真实长任务 checkpoint 样例）。
