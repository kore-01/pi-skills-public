# 开盘啦官方接口（kpls.kpl）

## 认证

`kpl_accounts.ini` 或 `KPL_ACCOUNTS_INI` 环境变量提供账号。`kpl.call()` 默认按 `var/account_cursor` 轮换主号/备号，
每次成功后推进游标；指定 `account=main_self` 则不轮换。`$env:KPLS_ACCOUNT_ROTATE='0'` 关闭轮换。

账号格式：

```ini
[main_self]
user=xxx
pwd=xxx

[main_self_2]
user=yyy
pwd=yyy
```

## 错误码

| errcode | 含义 | 处理 |
|---|---|---|
| `0` | 成功 | 正常 |
| `1130` / `1001` / `1002` / `1020` | 空结果 | 当作空数据，不算失败 |
| `998` / `1003` / `1004` / `1060` / `-1` / `-2` | 账号被限/失效 | 自动切另一账号重试 |

## 常用接口（api_id 见 `assets/apis.json`，152 条）

```
limit_up_realtime       实时涨停池
daily_limit_realtime    历取涨停池
longhubang_list         龙虎榜
auction_xxx             集合竞价系列
mood_num                市场情绪值
plate_xxx               板块/题材
zjlx_xxx                资金流向
```

调用：

```python
from kpls import kpl
kpl.call("limit_up_realtime")
kpl.call("daily_limit_realtime", PidType=1)
```

## 双账号轮换的意义

单账号高频调用会触发风控。轮换把请求摊到两个号上，均摊频率；
只有真遇到 998/1003/1004/1060/-1/-2 才立即切号兜底。
