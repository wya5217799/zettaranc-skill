"""
modules.strategies — 战法检测包

公共 API 通过本文件统一导出。业务逻辑位于各子模块：
  core.py              — 数据类型、数据库工具
  orchestrator.py      — 全量扫描流水线
  base_strategies.py   — 基础战法（B1/B2/B3/SB1）
  compound_strategies  — 复合战法
  sell_signals.py      — 逃顶信号
  kirin.py             — 麒麟会阶段分析
"""

from .core import (
    StrategyType, Priority, Action, StrategySignal,
    get_kline_data, get_db_connection,
    _klines_dict_to_daily, _dict_to_daily,
    _calc_kdj, _calc_bbi,
)

from .base_strategies import detect_b1, detect_b2, detect_b3, detect_sb1
from .compound_strategies import (
    detect_changan, detect_sifen_zhiyi_sanyin, detect_nana,
    detect_yidong_dilian, detect_pinghang, detect_kengqi, detect_duichen_va,
)
from .sell_signals import detect_s1, detect_s2, detect_s3, detect_brick_signals, _calc_dif
from .kirin import analyze_kirin_phase

from .orchestrator import (
    detect_all_strategies,
    get_latest_signal,
    format_signal,
    analyze_with_strategies,
    calculate_ma,
    calculate_kdj,
    calculate_bbi,
    _post_process_signals,
)

__all__ = [
    # Core types
    "StrategyType",
    "Priority",
    "Action",
    "StrategySignal",
    # Core utilities
    "get_kline_data",
    "get_db_connection",          # intentional re-export (used downstream)
    "_klines_dict_to_daily",      # intentional re-export (used downstream)
    "_dict_to_daily",
    "_calc_kdj",
    "_calc_bbi",
    # Base strategies
    "detect_b1",
    "detect_b2",
    "detect_b3",
    "detect_sb1",
    # Compound strategies
    "detect_changan",
    "detect_sifen_zhiyi_sanyin",
    "detect_nana",
    "detect_yidong_dilian",
    "detect_pinghang",
    "detect_kengqi",
    "detect_duichen_va",
    # Sell signals
    "detect_s1",
    "detect_s2",
    "detect_s3",
    "detect_brick_signals",
    "_calc_dif",
    # Kirin phase
    "analyze_kirin_phase",        # intentional re-export (used downstream)
    # Orchestrator — full pipeline
    "detect_all_strategies",
    "get_latest_signal",
    "format_signal",
    "analyze_with_strategies",
    # Backward-compat helpers (deprecated, kept for existing callers)
    "calculate_ma",
    "calculate_kdj",
    "calculate_bbi",
    "_post_process_signals",
]
