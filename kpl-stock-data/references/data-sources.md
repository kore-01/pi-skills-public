# 数据源字段、解码与降级（kpls.ts / sn / em / l2）

## 1. Tushare Pro（`kpls.ts`）

- 入口：`https://api.tushare.pro`，`pro(api_name, params, fields)` / `pro_raw()`。
- **本机证书链缺失**：首次 `CERTIFICATE_VERIFY_FAILED` 时自动降级为不校验 TLS（stderr 提示一次）。强制严格：`$env:TUSHARE_INSECURE='0'`。
- 代码转换 `to_ts_code`：`600xxx→.SH`、`000/002/300→.SZ`、`4/8 开头→.BJ`。
- 常用：`daily`、`daily_basic`、`stock_basic`、`trade_cal`、`index_daily`、`limit_list_d`、`moneyflow`、`hm_detail`、`top_inst`、`top_list`、`stk_factor[_pro]`、`cyq_perf`、`cyq_chips`、`kpl_concept_cons`、`dc_concept`、`stk_auction_o`。
- 辅助：`recent_trade_days()`、`last_trade_day()`、`bars(code, n, adj=)`（**升序**，可复权）。

## 2. 新浪（`kpls.sn`）

- 实时：`https://hq.sinajs.cn/list=sh600519,...` — **必须带 `Referer: https://finance.sina.com.cn`，返回 GBK**；未开盘返 0 值。
- 日K：`CN_MarketData.getKLineData`（含 `ma=no&datalen=N`）。
- 代码表：`Market_Center.getHQNodeData`（`node=hs_a/sh_a/sz_a`）。
- 排行：`sn.rank(node='hs_a', sort='amount'|'changepercent'|'turnoverratio'|'volume'|'mktcap', asc=False, num=N)` — 排序必须写成 `sort=字段&asc=0/1`（**不能写 `sort=-字段`**，否则退化为按 symbol 升序）。内部会过采样并按代码前缀过滤北交所（保留 60/68/00/30/20）。
- 字段名已与东财/开盘啦习惯对齐（`price/open/high/low/preclose/pct_chg/volume/amount/bid1/ask1/date/time`）。`volume` 单位=股，`amount` 单位=元。

## 3. 东方财富（`kpls.em`）

- 节点：`push2`（实时）、`push2his`（历史K线）、`push2delay`（延时批量）、`push2ex`（涨停/炸板池）。
- **`secid` 规则**：`6/9/5 开头→1.`；`0/3 开头→0.`；`4/8 开头→0.`。
- **解码关键（`_decode_quote`）**：
  - `push2 行情族`（`f43/f44/f45/f46/f60/f168/f169/f170/f50`）原始值为 **×100 整数** → **÷100**；
  - `clist/ulist 列表族`（`fltt=2`，`f2/f3/f4/f8/f10/f184`）**已是人类单位** → **不再除**。
    误除会得到 `price=0.4502`、`pct_chg=0.0328` 这类错值。
  - `main_net` = `f62`（元，原值）；`main_pct` = `f184`；`circ_mv`=`f21`、`total_mv`=`f20`（万元）。
- 字段：`f2 价 f3 涨跌幅 f4 涨跌额 f5 量 f6 额 f8 换手 f10 量比 f12/14 代码/名 f20/21 市值 f62 主力净额 f100 行业`。
- **本机实测**：`push2/push2his/push2delay` 常被拒（`RemoteDisconnected`），`push2ex`（涨停池/炸板池）可用。已内置**熔断**：连续 2 次失败 → 该节点 180s 内不再尝试（`em.available(host)`、`em.status()`），`$env:KPLS_EM_FORCE='1'` 可强制重试。

## 4. 开盘啦 L2（`kpls.l2`）

- 能力：`pankou`（盘口）、`bid`（买卖档）、`trend`（分时）、`monitor`（逐笔监控）、`weituo`（委托）、`chouma`（筹码）、`dadan_trend`（大单趋势）、`pack`、`summary`、`batch_monitor`。
- 成功判定：`raw["errcode"] == "0"`；`raw["code"]` 是股票代码字符串。
- 逐笔方向：`1 被动卖 / 2 主动买 / 3 被动买 / 4 主动卖`；`monitor` 汇总的 `active_buy` 取方向 2、`active_sell` 取方向 4，`net = 主动买 - 主动卖`。
- `money=2` 表示只看大单档（可调 1/2/3）。

## 5. 指标字段（`kpls.indicators.compute`）

| 字段 | 含义 |
|------|------|
| `ma` | `ma5/10/20/60`、`bull` 多头排列、`above_ma5/10/20`、`dist_ma5` 偏离%（正=在上方） |
| `macd` | `dif/dea/macd`、`golden` 金叉、`dead` 死叉 |
| `kdj` | `k/d/j` |
| `rsi14` / `atr14` | 相对强弱 / 波动率 |
| `boll` | `up/mid/low` + `pos` 通道位置%（>100 上轨外） |
| `vol_ratio5` | 对前 5 日均量的量比 |
| `pos20` | 20 日区间 `high/low/pos_pct` |
| `breakout20` | `ok` 20 日平台突破、`vol_ratio`、`strong` 放量确认 |
| `pullback_ma5` | `ok` 回踩 MA5、`dist_pct` |
| `limit` | `zt_count` 近 60 日涨停次数、`lianban`、`last_zt_days` |
| `divergence` | `price_new_high_no_vol`（价新高量缩）/`price_new_high_with_vol` |
| `chips_concentration` | 筹码集中度（需 Tushare `cyq_chips`） |
| `score` | 0-100 综合分（趋势+量能+位置+涨停基因） |
| `signals` | 人类可读标签列表（如「平台突破」「价涨量缩(背离)」） |

## 6. 候选池与降级链（`strategies.universe`）

```
zt        → 东财涨停池 → (失败/空) 开盘啦涨停池 kpl_zt_pool()
kpl_zt    → 开盘啦官方 daily_limit_realtime（info 表头行自动跳过）
xgb_zt    → 选股宝 limit_up_realtime（含连板数/封单/换手）
em_all / em_turnover / em_main / em_amount
          → 东财 clist(f3/f8/f62/f6) → (失败) 新浪 rank(changepercent/turnoverratio/amount)
sn_amount / sn_change / sn_turnover → 新浪 rank 直取
codes     → 显式代码列表
```

K 线/快照（`strategies.snapshot`）：东财 `em.bars` → 失败回落新浪 `sn.bars` → 得到 `data_source` 标记；`with_ts=True` 时再补 Tushare `stk_factor`。

**量纲对照**：新浪 `volume`=股、`amount`=元；Tushare `vol`=手、`amount`=千元；东财 `f5`=手、`f6`=元；开盘啦情绪 `qscln`=手量。
