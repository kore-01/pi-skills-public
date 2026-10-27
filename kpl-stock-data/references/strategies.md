# 策略选股手册（kpls.strategies）

CLI 用法：`python scripts\kpls.py strategy run <name> k=v ...`（参数用 `k=v`，未知参数自动忽略；无 `limit` 形参的策略会把 `limit` 映射为 `top`）。

```powershell
python "$S\scripts\kpls.py" strategy list
python "$S\scripts\kpls.py" strategy run zt_pool limit=10
python "$S\scripts\kpls.py" strategy run low_buy limit=60 bars=160 min_zt=1
python "$S\scripts\kpls.py" strategy run multi_confirm limit=5
python "$S\scripts\kpls.py" strategy run quote_compare --codes 600519,000001
```

Python：

```python
from kpls import strategies
strategies.run("zt_pool", limit=10)
strategies.run("low_buy", **{"limit": 60, "min_zt": 1})
strategies.describe("ladder")
```

## Tier1（免 Token，本地计算，14 个）

| 策略 | 参数（默认） | 逻辑 | 主要输出 |
|------|--------------|------|----------|
| `zt_pool` | `mode='em'` `day=None` `limit=200` | 涨停池；`mode=kpl` 走开盘啦官方 | `code/name/price/pct_chg/amount/turnover/first_seal/last_seal/open_times/boards/plate/seal_amount/circ_mv` |
| `first_board` | `day=None` `min_seal=0` `limit=60` | 涨停池中连板=1，按封单额过滤 | 同上 + `tag='首板'` |
| `ladder` | `day=None` `min_boards=2` `limit=80` | 连板天梯，按连板数分层排序 | `boards/code/name/...` |
| `broken` | `day=None` `min_open=1` `limit=60` | 炸板回落池，按开板次数排序 | 涨停池字段 + `open_times` |
| `auction_strong` | `top=20` `list_type='4'` | 开盘啦竞价池，按涨停委买额排序 | `code/name/pct_chg/wme/jjzf/jjje/jjhs/jjcje/lb` |
| `emotion` | 无 | 涨停/炸板家数 + 开盘啦情绪值 + 涨跌家数 + 三大指数 | `zt/zb/seal_rate/kpl_mood/rise_fall/indices` |
| `low_buy` | `limit=120` `min_zt=1` `ma=5` `tol=0.012` `max_vol_ratio=1.0` `bars=160` | 候选池→回踩 MA 附近 + 缩量 + 有涨停基因 | 指标快照 + `score/signals` |
| `breakout` | `limit=120` `bars=160` `min_vol_ratio=1.2` | 20 日新高 + 放量确认 | 指标快照 |
| `main_inflow` | `limit=60` `min_net=0` `with_flow=False` | 东财主力净额排行（`f62`）；EM 不可达时降级新浪成交额榜并标注 `note` | 行情 + `main_net/main_pct/industry` |
| `lhb` | `day=None` `limit=60` | 开盘啦龙虎榜 + Tushare `top_inst` 交叉验证 | `rows`(榜单) / `top_inst` |
| `multi_confirm` | `top=20`（`limit` 亦可）`bars=160` `min_main_net=0` | 涨停池（东财→选股宝→开盘啦）∩ 主力净额 ∩ 指标打分 | 指标快照 + `confirmed`（来源标签列表） |
| `trend_pick` | `limit=150` `bars=160` `min_score=60` | 多头排列 + 站上 MA20 + 打分达标 | 指标快照 |
| `l2_strong` | `codes=None` `pool_limit=20` `money=2` | 候选池逐只 L2 大单净额，取强势 | `big_net/big_buy/big_sell/orders` |
| `quote_compare` | `codes`（必填，列表或逗号串） | 开盘啦盘口 / 新浪 / 东财 多源对照，用于校验与排错 | 每源一行 |

输出统一含 `strategy`、`count`、`rows`、`sources`、`at`（本地时间）；数据源降级会体现在 `sources` / `note`。

## Tier2（需平台 Token，28 个透传）

`erjin3` `sanjin4` `sijin5` `lbc5plus` `firstboard_ignite` `distress_reversal` `broken_board`
`ladder_board` `ladder_watch` `ladder_watch_l2` `quant_pools` `composite` `surge_lowbuy`
`mood_board` `popularity` `kanpan` `zt_timeline` `darktrade_fund` `em_fflow` `ths_bigorder`
`l2_brief` `l2_desk` `auction_pool` `auction_buy_pool` `weimai_buy_pool`
`weimai_morning_bidding` `weimai_strategy_pool` `strategy_overview`

- 这些是**平台上已创建好的策略/看板**，本技能只做鉴权、双机 failover 与透传（不扣次，需 `kpl.fetch` 权益）。
- 参数直接透传：`strategy run ladder_watch limit=20` → `GET /api/ladder/watch?limit=20`。
- 名称→端点映射见 `platform-endpoints.md` §4。

## 选股组合建议

1. **情绪先行**：`emotion` 看涨停/炸板家数与封板率 → 决定是否进攻。
2. **主线定位**：`ladder` + `first_board` 找连板梯队与首板 → 锁定板块。
3. **个股精选**：候选池（`universe`）→ `low_buy`（回踩缩量）/ `breakout`（平台突破）→ `trend_pick`（趋势分）。
4. **资金确认**：`main_inflow`（EM 可用时）/ `l2_strong`（L2 大单）与 `multi_confirm`（多源共振）。
5. **交叉校验**：`quote_compare` 对关键标的做多源一致性核对，防单源错值。
