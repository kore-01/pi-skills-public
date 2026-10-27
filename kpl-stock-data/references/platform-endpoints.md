# py.590.net / i.590.net 平台端（kpls.py590）

## 1. 双机互备

| 主机 | 角色 | 出口 IP |
|------|------|---------|
| `https://py.590.net` | 主（212 机） | 193.112.101.212 |
| `https://i.590.net` | 备（55 机） | 111.170.173.55 |

两者数据一致、互为备份。`py590.call_path()` 按顺序尝试，全部失败才抛错；`py-health` 会同时汇报两机健康与出口 IP。可用 `KPL_PY_HOSTS="https://py.590.net,https://i.590.net"` 覆盖。

⚠️ **数据一致 ≠ 权益一致**：两机各自跑独立的 `kore-auth` + MySQL（212 侧 `m.590.net`/`py.590.net`，55 侧 `k.590.net`/`i.590.net`），用户与权益**不自动同步**。只在一台授权会出现「这台 200、那台 402」——**402 文案里的 `authUrl=https://k.590.net` 就是 55 机的线索**。用 `kore-mint --grant-all --mirror` 保持双机一致。

## 2. 鉴权模型

```
Authorization: Bearer <token>
X-App-Name: kpl-py
```

| 路由 | 要求 |
|------|------|
| `/health`、`/` | 免登录 |
| `/apis.json`、`/api/list`、`/api/info/*` | 需登录 |
| `/api/get/*` | 需登录 + **扣次**（illa 模式计数） |
| `/api/*/board`、`/api/ladder/*`、`/api/mood/*` 等 | 需登录 + `kpl.fetch` 权益，**不扣次** |

HTTP 语义：`401` → `TokenRequired`（token 缺失/过期/被拒），`402` → `EntitlementRequired`（无 `kpl.fetch` 权益）。

**三种 Token**

1. **本机内置长效 Token（默认，推荐）**：`assets\py_token.txt`，`sub=1(e07559, admin)`、`type=access`、**无 `sid`**（不受同端互踢影响）、`exp=2100-01-01`。配合 212/55 双机共 29 项终身权益（`assets\features.lifetime.txt`），`/api/*/board` 直过、**不扣次**。
2. **Kore access JWT**：登录 `m.590.net` 后从 devtools 复制，约 15 分钟有效（带 `sid`，会被同端登录踢掉）。
3. **当日 scoped token**：`POST /api/auth/export-token`（带 Kore JWT）换取，当日 23:59:59 前有效。
   ```powershell
   python "$S\scripts\kpls.py" py-export --kore-token <Kore登录JWT>   # 自动写入 assets\py_token.txt
   ```
   也可直接 `$env:KPL_PY_TOKEN='<token>'`（env 优先级高于文件）。

**铸造 / 轮换（工具零内置密钥）**

```powershell
$env:KORE_CN_SSH_PASSWORD='...'; $env:KORE_BACKUP_SSH_PASSWORD='...'
python "$S\scripts\kpls.py" kore-mint --check   # 只读体检（Token + 四域权益 + 两机目录；不健康退出码 2）
python "$S\scripts\kpls.py" kore-mint --auto    # 体检不健康才轮换（定时任务入口；健康则零写入）
python "$S\scripts\kpls.py" kore-mint --from-ssh --grant-all --mirror --verify   # 手动完整轮换
```

`kore_mint` 只从**环境变量 / CLI 参数**取 `JWT_SECRET` 与 SSH 口令（`--secret` 直传，或 `--from-ssh` 从主备机 `/opt/kore-auth/.env` 现读），本地手工 HS256 签发：`--grant-all` 给 user 1 写 29 项 `lifetime` 订阅，`--mirror` 把 212 的订阅镜像到 55，`--verify` 回验四域 `features` + 两机 `/api/list`。

> **已接定时任务**：Windows 计划任务 `KoreKplTokenRotate`（每日 09:35）执行 `%USERPROFILE%\.kore-ops\rotate-kore-token.ps1`（默认 `--auto`）；SSH 口令存该目录下 DPAPI 加密文件（仅本机本用户可解），日志按月落 `.kore-ops\logs\`。Token 使用超过 `KORE_TOKEN_MAX_AGE_DAYS=365` 天即判定需轮换。

## 3. 策略 / 看板端点（`py590.EXTRA_BOARDS`）

```
连板/天梯 : ladder/board  ladder/quant_pools  ladder/plate-top5  ladder/watch  ladder/watch_l2
            ladder/ticket_history
竞价      : auction-pool  auction-buy-pool  auction-hist/days  auction-hist/board
情绪/题材 : mood/board  plate-stocks/board*  popularity/board  kanpan/board
涨停时间轴: zt-timeline/board  broken-stocks/board
资金/大单 : flow_batch  flow_history  darktrade-fund/board  em-fflow/board*  ths-bigorder/board*
L2       : （`l2-brief` / `l2-desk` / `l2-desk/watch` 已下线返回 404 —— L2 请走本地 `l2s.py`）
选股      : composite-select/board  surge-lowbuy-pool  cyq
龙虎榜    : lhb-hist/days  lhb-hist/board
时段复盘  : premarket/board  open_review/board  intraday_pulse/board  tail_snapshot/board
            close_review/board
```

`*` = **必填参数**：`plate-stocks/board` 需 `plate=`（例 `801900`）；`em-fflow/board`、`ths-bigorder/board` 需 `code=`。缺参会得到带参数提示的错误（见 `py590.PARAM_HINTS`）。

用法：

```powershell
python "$S\scripts\kpls.py" py ladder/board --limit 20      # 也可直接 k=v 传参
python "$S\scripts\kpls.py" py mood/board
python "$S\scripts\kpls.py" py-list                          # 平台 /api/list 原始清单
python "$S\scripts\kpls.py" py -- api/info/ladder/board       # 单端点元信息
```

Python：

```python
from kpls import py590
py590.health()                      # 双机健康
py590.list_apis()                   # /api/list
py590.board("ladder/board", {"limit": 20})
py590.strategy_overview(["600519", "000001"])   # /api/strategy_overview
```

### 3.1 终身看盘（lifetime watch，2026-10-19 新增）

`/kits/watch/` 看板的后端端点，需终身授权（本机内置长效 Token 已带 `lifetime` 权益）：

| 端点（EXTRA_BOARDS 键） | 路径 | 参数 | 说明 |
|------|------|------|------|
| `lifetime/overview` | `/api/lifetime/watch/overview` | — | 实时总览：龙头池 pool(50) + 涨停梯队 layers(5板+~首板) + 情绪 |
| `lifetime/ladder` | `/api/lifetime/watch/ladder` | `date=` | 历史涨停梯队（指定日全量，layers 按连板数分层；不传 date 返回 available_days） |
| `lifetime/stock` | `/api/lifetime/watch/stock` | `code=` | 个股历史轨迹：track(梯队) + zt_hits(涨停命中) + flow(资金史) |
| `lifetime/quote` | `/api/lifetime/watch/quote` | `codes=` | 实时行情（新浪批量快照，逗号分隔多代码） |
| `lifetime/days` | `/api/lifetime/watch/days` | — | 归档交易日列表 |
| `lifetime/status` | `/api/lifetime/status` | — | 终身授权状态（lifetime/userId/display） |
| `lifetime/redeem` | `/api/lifetime/redeem` | `code=` | 兑换码兑换（如 KPLT-xxx） |

```powershell
python "$S\scripts\kpls.py" py lifetime/overview
python "$S\scripts\kpls.py" py lifetime/ladder date=2026-10-16
python "$S\scripts\kpls.py" py lifetime/stock code=600825
python "$S\scripts\kpls.py" py lifetime/quote codes=600519,000001
python "$S\scripts\kpls.py" py lifetime/days
```

Python：`py590.lifetime_overview()` / `lifetime_ladder(day)` / `lifetime_stock(code)` / `lifetime_quote(codes)` / `lifetime_days()` / `lifetime_status()` / `lifetime_redeem(code)`。

> 鉴权：这些端点仍走 `Authorization: Bearer <kore token>`；`KPLT-973M-R6XT-ECQK-Z6NN` 这类是**兑换码**（走 `lifetime/redeem`），不是 Bearer token。

## 4. Tier2 策略名 → 端点（`strategies.PLATFORM_STRATEGIES`，28 项；已剔除下线的 `l2_brief`/`l2_desk`）

| 策略名 | 端点 |
|--------|------|
| `erjin3` | `erjin3_board` |
| `sanjin4` | `sanjin4_board` |
| `sijin5` | `sijin5_board` |
| `lbc5plus` | `lbc5plus_board` |
| `firstboard_ignite` | `firstboard_ignite_board` |
| `distress_reversal` | `distress_reversal_board` |
| `broken_board` | `broken_stocks` |
| `ladder_board` | `ladder_board` |
| `ladder_watch` | `ladder/watch` |
| `ladder_watch_l2` | `ladder/watch_l2` |
| `quant_pools` | `ladder/quant_pools` |
| `composite` | `composite-select/board` |
| `surge_lowbuy` | `surge-lowbuy-pool` |
| `mood_board` | `mood/board` |
| `popularity` | `popularity/board` |
| `kanpan` | `kanpan/board` |
| `zt_timeline` | `zt-timeline/board` |
| `darktrade_fund` | `darktrade-fund/board` |
| `em_fflow` | `em-fflow/board` |
| `ths_bigorder` | `ths-bigorder/board` |
| `l2_brief` | `l2-brief` |
| `l2_desk` | `l2-desk` |
| `auction_pool` | `auction-pool` |
| `auction_buy_pool` | `auction-buy-pool` |
| `weimai_buy_pool` | `weimai_buy_pool` |
| `weimai_morning_bidding` | `weimai_morning_bidding` |
| `weimai_strategy_pool` | `weimai_strategy_pool` |
| `strategy_overview` | `strategy_overview`（POST，传 codes 列表） |

```powershell
python "$S\scripts\kpls.py" strategy run surge_lowbuy
python "$S\scripts\kpls.py" strategy run ladder_watch
```

> 平台侧策略/看板共约 115 条路由，完整清单以线上 `serve_http.py` 与 `py-list` 为准；本文件只列技能已对齐的部分。

## 5. Tier2 现状与降级

- **Tier2 已激活**：本机内置长效 Token（§2.1），212/55 双机各 29 项权益均为 `lifetime`，`/api/*/board` 可直调。2026-10-17 实测：`py-list`=152、`ladder/board`、`ladder/quant_pools`、`ladder/watch_l2`、`auction-pool`、`auction-buy-pool`、`mood/board`、`zt-timeline/board`、`surge-lowbuy-pool`、`darktrade-fund/board`、`composite-select/board`、`popularity/board`(181) 等**全部 200**。
- **唯一硬故障 = 双机权益不同步**：症状是「一台 200、另一台 `402 NO_CREDITS`」。修复：`kore-mint --grant-all --mirror` 后跑 `--verify`。
- **已下线**：`mood/cycle`、`l2-brief`、`l2-desk`、`l2-desk/watch` → `404`，已从技能清单移除。
- **瞬时失败**：`i.590.net` 偶发 TLS 握手失败（约 1/4 概率）；`ths-bigorder/board` 在 py.590 偶发上游 `502`。均由双机 failover 兜住，重试即可。
- **仍可降级 Tier1**：`401`（无 / 过期 token）会抛带指引的 `TokenRequired`；Tier1 覆盖涨停/炸板/连板/竞价/情绪/龙虎榜/资金/L2，**免 Token、不扣次**。
