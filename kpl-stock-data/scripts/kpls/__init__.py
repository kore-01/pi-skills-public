# -*- coding: utf-8 -*-
"""kpls — 股票数据与策略工具箱（开盘啦官方 + Tushare + 新浪 + 东财 + L2 + 平台策略）。"""
from __future__ import annotations

from . import (catalog, config, em, http, indicators, kpl, l2, py590, router, sn,
               strategies, ts)

__version__ = "1.0.0"

call = router.call

__all__ = [
    "catalog", "config", "em", "http", "indicators", "kpl", "l2", "py590", "router",
    "sn", "strategies", "ts", "call", "__version__",
]
