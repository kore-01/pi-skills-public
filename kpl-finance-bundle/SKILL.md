---
name: kpl-finance-bundle
description: KPL/开盘啦金融技能打包件索引（原目录「全面分析」）。内含三套技能包 —— 反转逻辑验证(turnaround)、superyouzi 游资短线投研、superyouzi-analysis-pipeline「全面分析 <代码>」流水线 —— 外加 bin/cron 定时任务与 deploy_bundle 一键部署件。当用户说「全面分析 600519」「游资/打板/连板/龙头/情绪周期/题材主线」「困境反转/抄底验证/这票能不能反转」，或要把这套技能部署到服务器（~/.hermes）、对接 py.590 L2、配置反转池盘中监控 cron 时使用。
---

# 全面分析 · KPL 金融技能打包件

> ⚠️ 本目录**没有可执行的技能正文**，只有 tar.gz 打包件 + 索引（本文件）+ 解出的部署件副本。
> **要干活，直接读权威源**：`D:\cf\kpl\kpl-cli\skills\finance\`（三套技能包的源目录，已核实与包内一致）。

## 1. 内容清单（2026-10-17 实测）

| 打包件 | 大小 | 内容 |
|---|---|---|
| `finance_skills_bundle.tar.gz` | 15,775,075 B（约 15 MB） | 250 个条目 = `skills/finance/{turnaround,superyouzi,superyouzi-analysis-pipeline}/` + `bin/rt_pool_monitor_cron.sh` + `cron/turnaround.crontab` |
| `deploy_bundle.tar.gz` | 4,086 B | 3 个文件 = `deploy_bundle/{deploy.sh, env.template, deploy_说明.md}` |
| `src/deploy_bundle/` | 9,944 B | 上面那个小包解出的**可读副本**（已入库；这三个文件在 `D:\cf\kpl` 下没有第二份） |

解包总览：**229 文件 / 29 目录 / 33,069,828 B**

| 技能包 | 文件数 | 字节 | 包内 SKILL.md | 定位 |
|---|---|---|---|---|
| `skills/finance/turnaround/` | 50 | 5,703,503 | 43,725 B | 反转逻辑验证（frontmatter name `反转逻辑验证`）：困境反转证据链 + 反转主选池 + 6 维因子引擎 + cron 闭环 |
| `skills/finance/superyouzi/` | 170 | 27,315,651 | 14,174 B | 游资短线投研助手：15 套交易框架 + 28 位评审团 + 本地取数脚本（szdata / py.590 网关） |
| `skills/finance/superyouzi-analysis-pipeline/` | 4 | 34,839 | 15,305 B | 「全面分析 <6 位代码>」全维度流水线：面板 + 10 维 fetch + 席位评分 + 13 套框架 + SQLite 落库 + 结构化报告 |

包内三个大件（别整包入库）：`superyouzi/report/fonts/LXGWWenKaiScreen.ttf` 25,673,994 B、`turnaround/data/reverse_stock.db` 4,616,192 B、`turnaround/data/board/board_20261007.json` 480,028 B。

## 2. 三条使用路径

### 2.1 直接读权威源（推荐，零解包）

```
D:\cf\kpl\kpl-cli\skills\finance\<包名>\SKILL.md      ← 读它，按它的说明执行
D:\cf\kpl\kpl-cli\skills\finance\<包名>\references\    ← 细节（API、cron、交易日历）
```

- `turnaround` 与 `superyouzi` 两套：源目录与包内**逐字节一致**（50 文件/5,703,503 B、170 文件/27,315,651 B）。
- `superyouzi-analysis-pipeline`：源已更新（SKILL.md 15,614 B > 包内 15,305 B）→ **以源为准**，包是 2026-10-07 快照。

### 2.2 需要打包件本体时解包（解到临时目录，不要解进技能目录）

```powershell
$dst = Join-Path $env:PI_SCRATCH_DIR 'bundle_x'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
tar -xzf "$env:USERPROFILE\.agents\skills\全面分析\finance_skills_bundle.tar.gz" -C $dst
tar -xzf "$env:USERPROFILE\.agents\skills\全面分析\deploy_bundle.tar.gz"         -C $dst
```

> Windows 上解包后**部分中文文件名会乱码**（`deploy_说明.md` → `deploy_璇存槑.md`、`上手指南.md` → `涓婃墜鎸囧崡.md`），属 UTF-8 文件名被按 GBK 解码的产物；Linux 服务器上 `tar xzf` 正常，需正确中文名时在服务器上解或事后重命名。

### 2.3 部署到指定服务器（~/.hermes）

`deploy.sh` 要求与 `finance_skills_bundle.tar.gz` **同目录**，然后 `bash deploy.sh`：

1. 解压到 `~`（得到 `~/skills`、`~/bin`、`~/cron`）
2. 检查/创建 `~/.hermes/.env`（`chmod 600`，模板里是占位符）
3. 装 `~/.hermes/bin/rt_pool_monitor_cron.sh`
4. `crontab ~/cron/turnaround.crontab`
5. 跑 11 项验证清单（三个 skill 目录、`rt_pool_engine.py`/`rt_pool_monitor.py`/`rt_outcome_backfill.py`、cron 已注册、`hermes` CLI、venv python、`.env` 权限）

```bash
# 目标机：装了 hermes agent 的那台（脚本写死 HOME=/home/ubuntu 与 venv 路径）
scp -P 5522 finance_skills_bundle.tar.gz deploy.sh env.template root@<host>:/tmp/kb/
ssh -p 5522 root@<host> 'bash /tmp/kb/deploy.sh ; nano ~/.hermes/.env'
```

> 部署目标是 **hermes agent 主机**（`~/.hermes/skills/finance/...`、`~/.hermes/bin/`、`~/cron/turnaround.crontab`），与 py.590 / i.590 平台机（`193.112.101.212` / `111.170.173.55`）**不是同一套东西**——动手前先确认目标机装了 hermes，别照着往平台机上摊。

## 3. 随包定时任务（`cron/turnaround.crontab`，CST，工作日）

| 时间 | 任务 |
|---|---|
| 21:30 一~五 | 收盘后反转复查（仅关注池 REVERSED/NEAR/EARLY）+ 飞书推送 |
| 周一 09:30 | 全市场快速补扫（断点续传，跳过已扫） |
| 09:25 一~五 | 备选池 → 主选池增量迁移（行业评级 ≥30 + 每行业前 2）+ 推 board JSON |
| 09:25→15:00 一~五 | 反转主选池盘中 6 维因子监控（每 30s，🟢/🔴 推飞书，同方向当日去重） |
| 15:30 一~五 | 主选 → 止盈（≥+15%）/ 止损（≤-3%）归档 + 推 board JSON |
| 15:35 一~五 | 盘中信号 outcome 回填（5/15/30 分钟价 vs 触发价，≥+3% 记达成） |

日志 `~/.hermes/cron/output/`；信号库 `~/.hermes/skills/finance/turnaround/data/rt_signal_log.sqlite`。

## 4. 三个技能包各认什么话（触发条件）

| 用户说 | 走向 |
|---|---|
| 「全面分析 000011」「分析 000678」 | `superyouzi-analysis-pipeline`：全维度流水线（跑面板 → 10 维 fetch → 席位评分 → 13 套框架 → 落库 → 报告） |
| 「今天市场情绪怎么样」「能不能做短线」「某板块是不是主线」「这票是不是杀猪盘」「持仓怎么办」 | `superyouzi`：短线复盘教练视角（情绪 / 题材 / 个股 / 持仓 / 风险排查） |
| 「反转」「困境反转」「抄底验证」「这票能不能反转」「是不是反转了」 | `turnaround`：反转证据链拆解（修复路径、时间窗口、失败边界、赔率） |

`turnaround` 与 `superyouzi` 互补：一个看财务/经营困境反转，一个看席位/情绪短线。

## 5. 坑与约束

- **打包件不入 git**：约 15 MB 二进制无法 diff，`.gitignore` 已忽略 `全面分析/*.tar.gz`；它们**只在本机留存**。换机器要么从 `D:\cf\kpl\kpl-cli` 重打，要么从本机拷；本目录入库的只有本索引 + `src/deploy_bundle/`。
- **别整包往技能库里塞**：解包 33 MB，远超技能/插件包建议上限（单文档 128 KB、整包 ≤16 MB；宿主只读 `SKILL.md` 文档本身）。大资源（字体 / SQLite / board JSON）留在权威源。
- **密钥**：`~/.hermes/.env` 需 `chmod 600` 并填真实 `TUSHARE_TOKEN`（模板里是 `your_tushare_token_here`）；不要把它拷进技能目录或知识库。
- **cron 环境很干净**：`rt_pool_monitor_cron.sh` 写死 `HOME=/home/ubuntu` 与 venv `PATH`，并 `export PYTHONPATH` 指向 superyouzi 的 `szdata`；换用户/换路径必须同步改。
- **数据源**：盘中监控走 py.590.net longhuvip L2（`SUPERYOUZI_USE_PY590=1`）。py.590 / i.590 免登录策略与需 Token 的 Tier2 端点的分工见技能 `kpl-stock-data`。
- `src/deploy_bundle/` 是这两份打包件里部署脚本的**唯一副本**（`D:\cf\kpl` 下无第二份），改动请同步回 tar 或权威源。

## 6. 归档信息

- 归档日期：2026-10-17（来源：KPL 金融技能包 hermes 部署版，含 2026-10-06/07 快照）
- 本索引为修复「042 检查点 · 全面分析/ 无 SKILL.md → 宿主扫描不到」而建：目录里只有 `.tar.gz` 时 PI-Desktop（agent-runtime）**不会**产生技能条目，也不会报错。
- 宿主技能发现规则（源码实测）：只认**根级 `*.md`** 与**一级目录里的 `SKILL.md`**；不递归、不读 `.gitignore`；单文档上限 128 KB。
