"""
价格模式识别包

将原 price_patterns.py (~1600行) 拆分为以下子模块:
- _calculators: 共享低级计算函数 (白线/黄线/RSL/DMI)
- _divergence_macd: MACD信号与背离检测
- _double_needle_gun: 双线/针/双枪/SB1/量价/滴滴/祖冲之
- _bricks_patterns: 砖型图系统与B点检测
- _misc_patterns: 关键K/图形/呼吸/高级战法

公共 API 与原 price_patterns.py 完全一致，所有外部导入路径不变。
"""

from ._calculators import (
    calculate_zg_white,
    calculate_dg_yellow,
    calculate_rsl,
    calculate_dmi,
)

from ._divergence_macd import (
    detect_divergence,
    detect_macd_signals,
)

from ._double_needle_gun import (
    detect_double_line_cross,
    detect_needle_20,
    detect_needle_30,
    detect_double_gun,
    detect_sb1_detailed,
    detect_volume_pattern,
    detect_didi,
    calculate_zuchong_target,
)

from ._bricks_patterns import (
    calculate_brick_value,
    calculate_brick_history,
    detect_brick_trend,
    detect_fanbao,
    detect_b1_today,
    detect_b2_today,
    detect_four_brick_system,
)

from ._misc_patterns import (
    detect_key_k,
    detect_violence_k,
    check_two_30_rule,
    detect_nana_chart,
    detect_golden_bowl,
    detect_breathing_structure,
    detect_sb1,
    detect_b3,
    detect_zaihou_chongjian,
    detect_yueyueyushi,
    detect_key_candle,
)

__all__ = [
    # _calculators
    "calculate_zg_white",
    "calculate_dg_yellow",
    "calculate_rsl",
    "calculate_dmi",
    # _divergence_macd
    "detect_divergence",
    "detect_macd_signals",
    # _double_needle_gun
    "detect_double_line_cross",
    "detect_needle_20",
    "detect_needle_30",
    "detect_double_gun",
    "detect_sb1_detailed",
    "detect_volume_pattern",
    "detect_didi",
    "calculate_zuchong_target",
    # _bricks_patterns
    "calculate_brick_value",
    "calculate_brick_history",
    "detect_brick_trend",
    "detect_fanbao",
    "detect_b1_today",
    "detect_b2_today",
    "detect_four_brick_system",
    # _misc_patterns
    "detect_key_k",
    "detect_violence_k",
    "check_two_30_rule",
    "detect_nana_chart",
    "detect_golden_bowl",
    "detect_breathing_structure",
    "detect_sb1",
    "detect_b3",
    "detect_zaihou_chongjian",
    "detect_yueyueyushi",
    "detect_key_candle",
]
