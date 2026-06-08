"""
选股与择时系统
实现 Z哥 的"三最原则"和每日五步工作流

Package layout:
  _models.py     — StockScore, MarketStatus
  _indicators.py — calculate_ma/vol_ma/kdj/bbi, is_perfect_pattern
  _data.py       — get_db_connection, get_all_stocks, get_recent_klines, get_market_status
  _scoring.py    — score_*, analyze_stock, _analyze_worker, _apply_p2_indicators
  _filters.py    — _filter_stock, _filter_*_strategy, _detect_*
  _screen.py     — screen_stocks, _PARALLEL_THRESHOLD
  _report.py     — format_stock_score, daily_workflow
  __main__.py    — CLI entry (python -m modules.screener)
"""

from ._models import StockScore, MarketStatus
from ._indicators import (
    calculate_ma,
    calculate_vol_ma,
    calculate_kdj,
    calculate_bbi,
    is_perfect_pattern,
)
from ._data import (
    get_db_connection,
    get_all_stocks,
    get_recent_klines,
    get_market_status,
)
from ._scoring import (
    score_b1_opportunity,
    score_trend,
    score_volume_pattern,
    score_risk,
    analyze_stock,
    _analyze_worker,
    _apply_p2_indicators,
    _adjust_total_score,
)
from ._filters import (
    _filter_stock,
    _filter_advanced_strategy,
    _filter_p2_strategy,
    _detect_super_b1,
    _detect_changan,
    _detect_b2_breakout,
    _detect_b3_consensus,
)
from ._screen import screen_stocks, _PARALLEL_THRESHOLD
from ._report import format_stock_score, daily_workflow

__all__ = [
    # models
    "StockScore",
    "MarketStatus",
    # indicators
    "calculate_ma",
    "calculate_vol_ma",
    "calculate_kdj",
    "calculate_bbi",
    "is_perfect_pattern",
    # data
    "get_db_connection",
    "get_all_stocks",
    "get_recent_klines",
    "get_market_status",
    # scoring
    "score_b1_opportunity",
    "score_trend",
    "score_volume_pattern",
    "score_risk",
    "analyze_stock",
    "_analyze_worker",
    "_apply_p2_indicators",
    "_adjust_total_score",
    # filters
    "_filter_stock",
    "_filter_advanced_strategy",
    "_filter_p2_strategy",
    "_detect_super_b1",
    "_detect_changan",
    "_detect_b2_breakout",
    "_detect_b3_consensus",
    # screen
    "screen_stocks",
    "_PARALLEL_THRESHOLD",
    # report
    "format_stock_score",
    "daily_workflow",
]
