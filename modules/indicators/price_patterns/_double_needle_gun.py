"""
双线战法、针形态、双枪战法、SB1、量价形态、滴滴、祖冲之目标价检测模块
"""

from typing import List, Dict, Any, Optional, Tuple

from ..core import (
    DailyData, calculate_kdj,
)
from ._calculators import calculate_zg_white, calculate_dg_yellow, calculate_rsl


def detect_double_line_cross(klines: List[DailyData]) -> Tuple[bool, bool]:
    """
    检测双线战法金叉死叉

    Returns:
        (is_gold_cross, is_dead_cross)
    """
    if len(klines) < 3:
        return False, False

    # 需要足够数据计算大哥线
    if len(klines) < 115:
        return False, False

    # 计算历史白线和大哥线
    white_values = []
    dg_values = []

    for i in range(60, len(klines) + 1):
        sub_klines = klines[:i]
        if len(sub_klines) >= 114:
            white = calculate_zg_white(sub_klines)
            dg = calculate_dg_yellow(sub_klines)
            white_values.append(white)
            dg_values.append(dg)

    if len(white_values) < 3:
        return False, False

    # 今天、昨天（双线金叉/死叉只需相邻两点）
    w_today = white_values[-1]
    w_yesterday = white_values[-2]

    d_today = dg_values[-1]
    d_yesterday = dg_values[-2]

    # 金叉：白线从下方上穿大哥线
    gold_cross = w_yesterday <= d_yesterday and w_today > d_today

    # 死叉：白线从上方下穿大哥线
    dead_cross = w_yesterday >= d_yesterday and w_today < d_today

    return gold_cross, dead_cross


def detect_needle_20(klines: List[DailyData]) -> Tuple[float, float, bool]:
    """
    检测单针下20信号（通达信标准）

    条件：短期RSL(3) <= 20 AND 长期RSL(21) >= 60
    即白线下20买：散户浮筹<20 且 主力控盘>60

    Returns:
        (rsl_short, rsl_long, is_needle_20)
    """
    if len(klines) < 22:
        return 50, 50, False

    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)

    is_needle = rsl_short <= 20 and rsl_long >= 60  # 对齐通达信

    return rsl_short, rsl_long, is_needle


def detect_needle_30(klines: List[DailyData]) -> bool:
    """
    检测单针下30信号（单针下20的迭代版）

    量化资金介入后阈值上移：
    - 红线(主力控盘) > 85
    - 白线(散户浮筹) < 30

    舍弃部分低位空间，换取更高确定性与入场频次
    """
    if len(klines) < 22:
        return False
    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)
    return rsl_long > 85 and rsl_short < 30


def _find_fangliang_yang_idx(
    klines: List[DailyData],
    start: int,
    stop: int,
) -> Optional[int]:
    """
    在 klines[start..stop) 内从后往前找第一根放量阳线（量比>=1.8，涨幅>=3%）。
    返回该根的索引，找不到返回 None。
    """
    for i in range(start, stop, -1):
        if i > 0:
            prev_vol = klines[i - 1].vol
            vol_ratio = klines[i].vol / prev_vol if prev_vol > 0 else 0
            if klines[i].pct_chg >= 3 and klines[i].close > klines[i].open and vol_ratio >= 1.8:
                return i
    return None


def _avg_mid_vol_ratio(klines: List[DailyData], from_idx: int, to_idx: int) -> float:
    """计算 klines[from_idx+1 .. to_idx) 各日相对前日的量比均值。"""
    ratios = []
    for i in range(from_idx + 1, to_idx):
        if i > 0:
            prev_vol = klines[i - 1].vol
            if prev_vol > 0:
                ratios.append(klines[i].vol / prev_vol)
    return sum(ratios) / len(ratios) if ratios else 0.0


def detect_double_gun(klines: List[DailyData]) -> Dict:
    """
    双枪战法检测

    图形特征：两根放量阳柱中间夹一堆缩量阴线
    本质：主力建仓确认 — 第一根试盘，中间洗盘，第二根确认

    规则：
    - 往前找最近一根放量阳线（第二枪）
    - 再往前找另一根放量阳线（第一枪）
    - 中间夹缩量小阴小阳（3-10天）
    - 第二枪前一日应有B1痕迹（J<13）
    """
    result: dict[str, Any] = {
        'is_double_gun': False,
        'double_gun_vol1': 0.0,
        'double_gun_vol2': 0.0,
        'double_gun_gap_days': 0,
    }
    if len(klines) < 15:
        return result

    n = len(klines)

    # 往前找最近一根放量阳线（第二枪），排除今天
    gun2_idx = _find_fangliang_yang_idx(klines, n - 2, max(0, n - 15))

    if gun2_idx is None or gun2_idx < 5:
        return result

    # 检查第二枪前一日是否有B1痕迹
    _, _, j_before_gun2 = calculate_kdj(klines[:gun2_idx])
    has_b1_before = j_before_gun2 < 20

    # 从第二枪往前找第一枪
    gun1_idx = _find_fangliang_yang_idx(klines, gun2_idx - 3, max(0, gun2_idx - 12))

    if gun1_idx is None:
        return result

    gap_days = gun2_idx - gun1_idx

    # 检查中间是否缩量
    avg_mid_vol = _avg_mid_vol_ratio(klines, gun1_idx, gun2_idx)
    if avg_mid_vol == 0.0:
        return result
    is_shrink_mid = avg_mid_vol < 1.2  # 中间平均量比 < 1.2

    # 计算两枪的量比
    g1_prev = klines[gun1_idx - 1] if gun1_idx > 0 else None
    g2_prev = klines[gun2_idx - 1] if gun2_idx > 0 else None
    vol1: float = klines[gun1_idx].vol / g1_prev.vol if g1_prev and g1_prev.vol > 0 else 0.0
    vol2: float = klines[gun2_idx].vol / g2_prev.vol if g2_prev and g2_prev.vol > 0 else 0.0

    if is_shrink_mid and has_b1_before and 3 <= gap_days <= 10:
        result['is_double_gun'] = True
        result['double_gun_vol1'] = round(vol1, 1)
        result['double_gun_vol2'] = round(vol2, 1)
        result['double_gun_gap_days'] = gap_days

    return result


def _find_big_drop_idx(klines: List[DailyData], start: int, stop: int) -> Optional[int]:
    """
    在 klines[start..stop) 内从后往前找放量大阴线（跌幅>3%，量比>=1.5，收阴）。
    返回该根的索引，找不到返回 None。
    """
    for i in range(start, stop, -1):
        if i > 0:
            prev_vol = klines[i - 1].vol
            vol_ratio = klines[i].vol / prev_vol if prev_vol > 0 else 0
            if klines[i].pct_chg <= -3 and vol_ratio >= 1.5 and klines[i].close < klines[i].open:
                return i
    return None


def _has_shrink_after_drop(klines: List[DailyData], drop_idx: int) -> bool:
    """检查 drop_idx 后至末尾每根K线量是否均 < drop_idx 量的 70%。"""
    drop_vol = klines[drop_idx].vol
    for i in range(drop_idx + 1, len(klines)):
        if klines[i].vol > drop_vol * 0.7:
            return False
    return True


def _is_n_type_structure(klines: List[DailyData], before_idx: int) -> bool:
    """判断 before_idx 前的低点是否呈 N 型抬高结构。"""
    if before_idx < 5:
        return False
    pre_lows = [klines[i].low for i in range(max(0, before_idx - 10), before_idx)]
    if len(pre_lows) < 3:
        return False
    first_half = pre_lows[:len(pre_lows) // 2]
    second_half = pre_lows[len(pre_lows) // 2:]
    return min(second_half) < min(first_half)


def detect_sb1_detailed(klines: List[DailyData]) -> Dict:
    """
    超级B1独立检测

    形态流程：
    N型上涨 → 缩量回调 → 标准B1触发 → 突然放量大阴线击穿止损位 →
    缩量企稳 + J值大负值 → 反转K线确认 → 入场

    只赌一次，不可重复博弈
    """
    result = {
        'is_sb1_detailed': False,
    }
    if len(klines) < 15:
        return result

    n = len(klines)
    today = klines[-1]
    _, _, j_today = calculate_kdj(klines)

    # 往前找放量大阴线（击穿止损位）
    big_drop_idx = _find_big_drop_idx(klines, n - 2, max(0, n - 10))

    if big_drop_idx is None:
        return result

    # 大阴线后缩量企稳（1-3天）
    days_after_drop = n - 1 - big_drop_idx
    if days_after_drop < 1 or days_after_drop > 3:
        return result

    # 检查大阴线后是否缩量
    if not _has_shrink_after_drop(klines, big_drop_idx):
        return result  # 没有缩量

    # J值大负值
    if j_today > -5:
        return result

    # 反转K线确认（十字星或小阳）
    body = abs(today.close - today.open)
    prev_close = klines[-2].close if len(klines) > 1 else today.close
    body_pct = body / prev_close * 100 if prev_close > 0 else 0
    is_reversal = body_pct <= 2 or (today.pct_chg > 0 and today.close > today.open)

    if not is_reversal:
        return result

    # 检查大阴线前是否有N型上涨结构
    if _is_n_type_structure(klines, big_drop_idx):
        result['is_sb1_detailed'] = True

    return result


def detect_volume_pattern(today: DailyData, yesterday: Optional[DailyData] = None) -> Dict[str, bool]:
    """
    检测量价形态

    Args:
        today: 今日数据
        yesterday: 昨日数据

    Returns:
        形态检测结果
    """
    result = {
        'is_beidou': False,           # 倍量
        'is_suoliang': False,        # 缩量
        'is_jiayin_zhenyang': False, # 假阴真阳
        'is_jiayang_zhenyin': False, # 假阳真阴
        'is_fangliang_yinxian': False # 放量阴线
    }

    if yesterday is None:
        return result

    # 倍量：今日量 > 昨日量 × 2
    if today.vol >= yesterday.vol * 2:
        result['is_beidou'] = True

    # 缩量：今日量 < 昨日量 × 0.5
    if today.vol <= yesterday.vol * 0.5:
        result['is_suoliang'] = True

    # 假阴真阳：收 < 开 but 收 > 昨收
    if today.close < today.open and today.close > today.prev_close:
        result['is_jiayin_zhenyang'] = True

    # 假阳真阴：收 > 开 but 收 < 昨收
    if today.close > today.open and today.close < today.prev_close:
        result['is_jiayang_zhenyin'] = True

    # 放量阴线：下跌 + 放量
    if today.close < today.prev_close and today.vol > yesterday.vol * 1.5:
        result['is_fangliang_yinxian'] = True

    return result


def detect_didi(klines: List[DailyData]) -> Dict:
    """
    滴滴战法检测（高位连续两根阴线下台阶）

    来源：Z哥交易体系 3.11 / trading-core.md
    定义：高位连续两根阴线，第二根收盘价 < 第一根最低价，量未明显萎缩。
    性质：最高优先级卖出信号，绕过防卖飞直接清仓。

    条件：
    1. 第一根阴线（收盘价 < 开盘价）
    2. 第二根阴线（收盘价 < 开盘价）
    3. 第二根收盘价 < 第一根最低价（下台阶）
    4. 第二根成交量 >= 第一根成交量 × 0.8（量没明显缩）
    5. 当前处于相对高位（收盘价 >= 近期20天最高价的 80%）

    Args:
        klines: K线数据（至少2根）

    Returns:
        {'is_didi': bool, 'first_low': float, 'second_close': float, 'volume_ratio': float}
    """
    if len(klines) < 2:
        return {'is_didi': False}

    today = klines[-1]
    yesterday = klines[-2]

    # 两根都是阴线（严格：收盘价 < 开盘价）
    is_yin_1 = yesterday.close < yesterday.open
    is_yin_2 = today.close < today.open

    # 下台阶：第二根收盘 < 第一根最低
    is_down_step = today.close < yesterday.low

    # 量未明显萎缩（今天量 >= 昨天量 × 0.8）
    is_volume_ok = today.vol >= yesterday.vol * 0.8 if yesterday.vol > 0 else False

    # 高位判断（当前 >= 近20天最高价的 80%）
    recent = klines[-20:] if len(klines) >= 20 else klines
    recent_high = max(k.high for k in recent)
    is_high = today.close >= recent_high * 0.8

    if is_yin_1 and is_yin_2 and is_down_step and is_volume_ok and is_high:
        return {
            'is_didi': True,
            'first_low': round(yesterday.low, 2),
            'second_close': round(today.close, 2),
            'volume_ratio': round(today.vol / yesterday.vol, 2) if yesterday.vol > 0 else 0,
            'recent_high': round(recent_high, 2)
        }

    return {'is_didi': False}


def calculate_zuchong_target(klines: List[DailyData], lookback: int = 60) -> Dict:
    """
    祖冲之法 —— 主力目标价计算

    来源：advanced-patterns.md「坑里起好货」
    核心逻辑：填坑意味着解放前期套牢盘，主力要拉到足够高度才有利润。
    公式：目标价 = 2a - b
      a = 近期高点（填坑前的高点）
      b = 近期低点（坑底）

    应用：
    - 填大坑过程中遇到 BBI 下 2 根 K 线可以扛一会儿
    - 填小坑到达目标价位及时卤煮（止盈）

    Args:
        klines: K线数据
        lookback: 回望天数（默认60天）

    Returns:
        {'target': float, 'a': float, 'b': float, 'current': float, 'upside_pct': float}
    """
    if len(klines) < 10:
        return {'target': 0, 'a': 0, 'b': 0, 'current': 0, 'upside_pct': 0}

    recent = klines[-lookback:] if len(klines) >= lookback else klines

    highs = [k.high for k in recent]
    lows = [k.low for k in recent]

    a = max(highs)   # 近期高点
    b = min(lows)    # 近期低点
    current = klines[-1].close

    target = 2 * a - b
    upside_pct = (target - current) / current * 100 if current > 0 else 0

    return {
        'target': round(target, 2),
        'a': round(a, 2),
        'b': round(b, 2),
        'current': round(current, 2),
        'upside_pct': round(upside_pct, 1)
    }
