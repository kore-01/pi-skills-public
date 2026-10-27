---
name: kpl-stock-data
description: A股股票数据 + 指标 + 策略选股工具箱（开盘啦官方接口 / Tushare Pro / 新浪 / 东方财富 / 开盘啦 L2 / py.590 平台已配置策略）。当需要涨停池、连板天梯、龙虎榜、L2 大单、资金流、K线与技术指标、多源行情对照、或调用 py.590/i.590 平台现成策略看板时使用。
---

# kpl-stock-data · A股数据与策略选股

自用工具箱：**官方接口取数 → 本地指标计算 → 策略选股**，并透传平台（`py.590.net` / `i.590.net` 双机互备）已创建好的策略与看板。

零第三方依赖（标准库 urllib），Python 3.9+（本机 3.14）。

## 1. 快速开始

```powershell
$S = "C:\Users\Administrator\.agents\skills\kpl-stock-data"

python "$S\scripts\kpls.py" doctor -v          # 全链路自检（账号/五源/平台）
python "$S\scripts\kpls.py" test               # 免 Token 实盘取数冒烟
python "$S\scripts\kpls.py" accounts           # 内置开盘啦账号（脱敏）
python "$S\scripts\kpls.py" strategy list      # 策略清单（Tier1 14 + Tier2 28）
python "$S\scripts\kpls.py" indicator list     # 指标清单
python "$S\scripts\kpls.py" catalog -q 涨停 --limit 20   # 接口目录（152 条（已含 kpl.590.net 官方文档 69 接口全集））
```

Python 里当库用：

```python
import sys; sys.path.insert(0, r"C:\Users\Administrator\.agents\skills\kpl-stock-data\scripts")
from kpls import kpl, ts, sn, em, l2, indicators, strategies, router

strategies.run("zt_pool", limit=10)                 # 涨停池
strategies.run("low_buy", limit=80)                 # 低吸
indicators.compute(ts.bars("600519", 160), code="600519")
router.call("mood_num")                             # 目录驱动调用（自动路由到源）
```

## 2. 数据源与降级链

| 源 | 模块 | 能力 | 鉴权 |
|----|------|------|------|
| 开盘啦官方 | `kpl` | 152 条目录（**已含 kpl.590.net 官方文档 69 接口全集**）：实时/历取/涨停池/L2/龙虎榫/竞价/板块/情绪/题材/北向 |
| Tushare Pro | `ts` | 日线（含复权）/基本面对账/涨停榜/资金流/筹码/概念 | 内置 token |
| 新浪 | `sn` | 实时快照/批量/日K/代码表/排行 | 免登录 |
| 东方财富 | `em` | 行情/排行/资金流/涨停池/炸板池 | 免登录 |
| 开盘啦 L2 | `l2` | 盘口/逐笔/大单/委托/筹码/监控 | 用开盘啦账号 |
| 平台 | `py590` | Tier2：29 项平台策略/看板（**已激活**） | 内置长效 Kore Token（`assets\py_token.txt`）；env/当日 scoped token 亦可 |

**自动降级（本机实测）**：东财 `push2/push2his` 行情族常被拒或超时 → 已内置熔断（`em.available()`、`KPLS_EM_FORCE=1` 可强制重试），K 线自动回落新浪（`indicator --source auto` 顺序 em→sn→ts），候选池自动回落新浪排行（`universe` 内建），Tushare 证书链缺失时自动降级不校验 TLS（可关：`TUSHARE_INSECURE=0`）。

## 3. 常用命令

```powershell
# 开盘啦官方（api_id 来自 asset/apis.json；params 用 k=v）
python "$S\scripts\kpls.py" kpl mood_num
python "$S\scripts\kpls.py" kpl daily_limit_realtime PidType=1
python "$S\scripts\kpls.py" kpl longhubang_list Date=2026-10-16
python "$S\scripts\kpls.py" api limit_up_realtime            # 通用路由（自动选源）

# Tushare / 新浪 / 东财
python "$S\scripts\kpls.py" ts daily symbol=600519 start_date=20261001 --limit 5
python "$S\scripts\kpls.py" sn quote 600519
python "$S\scripts\kpls.py" sn rank --sort changepercent --limit 20
python "$S\scripts\kpls.py" em zt --date 20261016
python "$S\scripts\kpls.py" em clist --fid f62 --pz 20        # 主力净额排行

# L2 / 指标 / 策略 / 多源对照
python "$S\scripts\kpls.py" l2 600519 --money 2
python "$S\scripts\kpls.py" indicator 600519 --bars 160
python "$S\scripts\kpls.py" strategy run zt_pool limit=10
python "$S\scripts\kpls.py" strategy run multi_confirm limit=5
python "$S\scripts\kpls.py" quote 600519 000001
```

平台（**已内置长效 Token，免登录**；双机自动 failover）：

```powershell
python "$S\scripts\kpls.py" py-health                  # 双机 /health（含 auth 状态）
python "$S\scripts\kpls.py" py-list                     # 平台 /api/list（152 条）
python "$S\scripts\kpls.py" py ladder/board             # 连板天梯看板（rows≈61）
python "$S\scripts\kpls.py" py popularity/board         # 综合人气榜（rows≈181）
python "$S\scripts\kpls.py" py plate-stocks/board plate=801900
python "$S\scripts\kpls.py" py em-fflow/board code=600519
python "$S\scripts\kpls.py" py lifetime/overview          # 终身看盘·实时总览（龙头池+涨停梯队+情绪）
python "$S\scripts\kpls.py" py lifetime/ladder date=2026-10-16   # 历史涨停梯队（指定日全量）
python "$S\scripts\kpls.py" py lifetime/stock code=600825     # 个股历史轨迹
python "$S\scripts\kpls.py" py lifetime/quote codes=600519,000001  # 实时行情（新浪快照）
python "$S\scripts\kpls.py" py lifetime/days                 # 归档交易日列表
python "$S\scripts\kpls.py" strategy run surge_lowbuy   # Tier2 透传
python "$S\scripts\kpls.py" kore-mint --from-ssh --grant-all --mirror --verify  # 手动完整轮换（重铸+授权+镜像+校验）
python "$S\scripts\kpls.py" kore-mint --check           # 只读体检（不写库；不健康退出码 2）
python "$S\scripts\kpls.py" kore-mint --auto            # 体检不健康才自动轮换（定时任务入口）
python "$S\scripts\kpls.py" py-export --kore-token <Kore登录JWT>                # 备选：当日 scoped
```

> 预置凭证：`assets\py_token.txt`（sub=1/e07559/admin，**无 sid → 不会同端互踢**，exp=2100-01-01）；平台 29 项权益（清单 `assets\features.lifetime.txt`）在 **212 与 55 两台**均授权为 `lifetime`（订阅模式，不扣次）。

## 4. 指标（本地计算，`indicators`）

`sma/ema`、`macd`、`kdj`、`rsi14`、`boll`、`atr14`、`vol_ratio5`、`pos20`、`breakout20`、`pullback_ma5`、`limit`（涨停基因）、`divergence`、`chips_concentration`（需 Tushare）、`score`（0-100 综合）、`signals`（信号标签）。字段详解见 `references/data-sources.md`。

## 5. 策略选股

- **Tier1（免 Token，本地 14 个）**：`zt_pool` `first_board` `ladder` `broken` `auction_strong` `emotion` `low_buy` `breakout` `main_inflow` `lhb` `multi_confirm` `trend_pick` `l2_strong` `quote_compare`。
- **Tier2（平台 Token，28 个透传；`assets\py_token.txt` 已就绪）**：`erjin3` `sanjin4` `sijin5` `lbc5plus` `weimai_*` `distress_reversal` `firstboard_ignite` `ladder_board`/`ladder_watch`/`ladder_watch_l2`/`quant_pools` `broken_board` `composite` `surge_lowbuy` `mood_board` `popularity` `kanpan` `zt_timeline` `darktrade_fund` `em_fflow`(需 `code=`) `ths_bigorder`(需 `code=`) `plate-stocks`(需 `plate=`) `auction_pool`/`auction_buy_pool` `strategy_overview`。`l2_brief`/`l2_desk`/`mood_cycle` 平台已下线（404）。

参数与输出字段见 `references/strategies.md`；平台端点见 `references/platform-endpoints.md`。

## 6. 配置（Token 安全）

| 项 | 优先级 |
|----|--------|
| 开盘啦账号 | env `KPL_ACCOUNTS_INI` → `D:\cf\kpl\config\kpl_accounts.ini` → `assets\kpl_accounts.ini` |
| Tushare | env `TUSHARE_TOKEN` → `assets\tushare.token` → ini `[py590]` → `D:\cf\趋势分析\.env` |
| 平台 Token | env `KPL_PY_TOKEN`/`KPL_EXPORT_TOKEN`/`KPL_KORE_TOKEN` → `assets\py_token.txt` → ini |
| 平台主机 | env `KPL_PY_HOSTS`（逗号分隔）→ 默认 `https://py.590.net,https://i.590.net` |

> **开盘啦双账号按次轮换（默认开）**：`kpl.call()` 每次成功后推进游标 `var/account_cursor`，下一次从另一个账号打头（主号 ⇄ 备号交替，均摊频率）；真遇 `998/1003/1004/1060/-1/-2` 再自动切号兜底。指定 `account=main_self` 则不轮换；关闭轮换 `$env:KPLS_ACCOUNT_ROTATE=0`。

> **真实 Token 只放在 `assets/`（本机）或环境变量里，禁止写入 `D:\cf\knowledge`、commit、或任何共享文档。**

## 7. 目录结构

```
kpl-stock-data/
├── SKILL.md
├── assets/    apis.json(152 条接口目录（已含 kpl.590.net 官方文档 69 接口全集）) kpl_accounts.ini tushare.token py_token.txt features.lifetime.txt
├── references/ platform-endpoints.md kpl-official-api.md data-sources.md strategies.md
└── scripts/   kpls.py(CLI)  kpls/{config,http,catalog,kpl,ts,sn,em,l2,indicators,strategies,py590,kore_mint,router}.py
```

## 8. 排错

| 现象 | 处理 |
|------|------|
| `东财 push2* 不可达` | 熔断生效中，等 180s 或 `$env:KPLS_EM_FORCE=1`；数据已自动回落新浪 |
| `Tushare 证书校验失败` | 自动降级 TLS（提示一次）；想强制严格：`$env:TUSHARE_INSECURE=0` |
| `缺少平台 Token` | 本机已预置 `assets\py_token.txt`；如被清空用 `kore-mint` 重铸，或 `py-export` 换当日 token，或改用 Tier1 |
| `402 NO_CREDITS / 需开通月卡` | 权益库不同步：212（m./py.590）与 55（i./k.590）是**两台独立 MySQL**；用 `kore-mint --grant-all --mirror` 补齐双机 |
| 开盘啦 `errcode` 非 0 | 1130/1001/1002/1020 视为空结果；998/1003/1004/1060/-1/-2 自动切另一账号 |
| 输出乱码 | 先 `$env:PYTHONIOENCODING='utf-8'`，或重定向到 UTF-8 文件再读 |

## 9. 定时任务：Token 到期自动轮换

已注册 Windows 计划任务 **`KoreKplTokenRotate`**（每日 09:35 + `StartWhenAvailable`；当前用户登录时运行）：

| 项 | 位置 |
|----|------|
| 任务 | `KoreKplTokenRotate`（`Get-ScheduledTask KoreKplTokenRotate`） |
| 脚本 | `%USERPROFILE%\.kore-ops\rotate-kore-token.ps1`（`-Check` 只体检 / `-Force` 强制重铸） |
| 凭据 | `%USERPROFILE%\.kore-ops\ssh-cli.cred.xml`（**DPAPI 加密**，仅本机本用户可解，ACL 已收紧） |
| 日志 | `%USERPROFILE%\.kore-ops\logs\rotate-YYYY-MM.log`（按月归档，UTF-8） |

行为：默认 `--auto` = 先体检（Token 声明 + 四域权益 + 两机 `/api/list`），**健康则零写入退出**；不健康或 Token 已用超过 `KORE_TOKEN_MAX_AGE_DAYS=365` 天才自动重铸 + 授权 + 双机镜像 + 复验。脚本与凭据**不内置任何密钥**：`JWT_SECRET` 每次由 SSH 从 `/opt/kore-auth/.env` 现读，不落盘。

```powershell
Start-ScheduledTask -TaskName KoreKplTokenRotate         # 手动触发
Get-ScheduledTaskInfo  -TaskName KoreKplTokenRotate      # 退出码（0=正常，2=不健康未修复）
powershell -File "$env:USERPROFILE\.kore-ops\rotate-kore-token.ps1" -Check   # 只读体检
```
