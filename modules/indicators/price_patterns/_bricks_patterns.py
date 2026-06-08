"""
砖型图系统与B点检测模块
"""

from typing import List, Dict, Any, Tuple

from ..core import (
    DailyData, calculate_ma, calculate_sma_series, calculate_slope, calculate_kdj,
)
from ._calculators import calculate_zg_white


def calculate_brick_value(klines: List[DailyData]) -> float:
    """
    计算砖型图数值（通达信标准公式 - 短期砖型图指标v2026）

    VAR1A = (HHV(HIGH,4) - CLOSE) / (HHV(HIGH,4) - LLV(LOW,4)) * 100 - 90
    VAR2A = SMA(VAR1A, 4, 1) + 100
    VAR3A = (CLOSE - LLV(LOW,4)) / (HHV(HIGH,4) - LLV(LOW,4)) * 100
    VAR4A = SMA(VAR3A, 6, 1)
    VAR5A = SMA(VAR4A, 6, 1) + 100
    VAR6A = VAR5A - VAR2A
    砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    """
    if len(klines) < 12:
        return 0

    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]

    # 构建 VAR3A 序列（需要至少 6 个值来算 SMA(VAR3A,6,1)）
    var3a_list: list[float] = []
    for i in range(3, len(klines)):  # HHV/LLV 需要 4 天，所以从索引 3 开始
        hhv4 = max(highs[max(0, i-3):i+1])
        llv4 = min(lows[max(0, i-3):i+1])
        if hhv4 == llv4:
            v3 = 50.0
        else:
            v3 = (closes[i] - llv4) / (hhv4 - llv4) * 100
        var3a_list.append(v3)

    if len(var3a_list) < 6:
        return 0

    # VAR4A = SMA(VAR3A, 6, 1) —— 递推序列，每个点承接前一个结果
    var4a_list = calculate_sma_series(var3a_list, 6, 1)

    if len(var4a_list) < 6:
        return 0

    # VAR5A = SMA(VAR4A, 6, 1) + 100 —— 递推序列
    var5a_list = calculate_sma_series(var4a_list, 6, 1)
    var5a = var5a_list[-1] + 100

    # 构建 VAR1A 序列
    var1a_list = []
    for i in range(3, len(klines)):
        hhv4 = max(highs[max(0, i-3):i+1])
        llv4 = min(lows[max(0, i-3):i+1])
        if hhv4 == llv4:
            v1: float = -90.0
        else:
            v1 = (hhv4 - closes[i]) / (hhv4 - llv4) * 100 - 90.0
        var1a_list.append(v1)

    if len(var1a_list) < 4:
        var2a = (var1a_list[-1] if var1a_list else -90) + 100
    else:
        # VAR2A = SMA(VAR1A, 4, 1) + 100 —— 递推序列
        var2a_list = calculate_sma_series(var1a_list, 4, 1)
        var2a = var2a_list[-1] + 100

    # VAR6A = VAR5A - VAR2A
    var6a = var5a - var2a

    # 砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    brick = var6a - 4 if var6a > 4 else 0

    return round(brick, 2)


def calculate_brick_history(klines: List[DailyData], lookback: int = 20) -> Tuple[str, int]:
    """
    计算砖型图趋势（连续红砖/绿砖数量）

    通达信公式逻辑（与官方一致）：
    - 红砖：今日砖值 >= 昨日砖值（动量上涨）→ COLORRED
    - 绿砖：今日砖值 < 昨日砖值（动量下跌）→ COLOR00FF00

    Args:
        klines: K线数据
        lookback: 回溯天数

    Returns:
        (趋势状态: RED/GREEN/NEUTRAL, 连续砖数)
    """
    if len(klines) < 10:
        return "NEUTRAL", 0

    # 计算历史砖值序列（对比昨日大小判断红绿）
    # 1=红(涨), -1=绿(跌), 0=平
    brick_colors = []
    prev_brick = None

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)

        if prev_brick is not None:
            if brick_val >= prev_brick:
                brick_colors.append(1)   # 红砖 = 上涨
            else:
                brick_colors.append(-1)  # 绿砖 = 下跌
        prev_brick = brick_val

    if not brick_colors:
        return "NEUTRAL", 0

    # 从最新往前数连续同色砖
    current_color = brick_colors[-1]
    if current_color == 0:
        return "NEUTRAL", 0

    count = 1
    for i in range(len(brick_colors) - 2, -1, -1):
        if brick_colors[i] == current_color:
            count += 1
        else:
            break

    trend = "RED" if current_color > 0 else "GREEN"
    return trend, count


def detect_brick_trend(klines: List[DailyData]) -> bool:
    """
    检测命值趋势是否上升

    条件：SLOPE(命值, 7) > -0.02 AND 运值 > 命值
    """
    if len(klines) < 115:
        return False

    closes = [k.close for k in klines]

    # 计算命值序列
    ming_values = []
    for i in range(113, len(klines)):
        sub = closes[:i+1]
        ma14 = calculate_ma(sub, 14)
        ma28 = calculate_ma(sub, 28)
        ma57 = calculate_ma(sub, 57)
        ma114 = calculate_ma(sub, 114)
        ming = (ma14 + ma28 + ma57 + ma114) / 4
        ming_values.append(ming)

    if len(ming_values) < 8:
        return False

    # 使用正确的 SLOPE 函数计算7日斜率
    slope = calculate_slope(ming_values, 7)

    # 计算当前运值和命值
    current_ming = ming_values[-1]
    yun_zhi = calculate_zg_white(klines)

    return slope > -0.02 and yun_zhi > current_ming


def detect_fanbao(klines: List[DailyData]) -> bool:
    """
    检测精准反包信号

    条件：
    1. 今天红柱（砖型图上涨）
    2. 昨天绿柱（砖型图下跌）
    3. 今天砖型图超过昨日绿柱2/3位置
    """
    if len(klines) < 4:
        return False

    brick_today = calculate_brick_value(klines)
    brick_yesterday = calculate_brick_value(klines[:-1])
    brick_before = calculate_brick_value(klines[:-2]) if len(klines) >= 3 else 0

    # 今天红柱
    is_red = brick_today > brick_yesterday
    # 昨天绿柱
    is_green_yesterday = brick_yesterday < brick_before
    # 昨天绿柱的实体高度
    lzgd = max(brick_yesterday, brick_before) - min(brick_yesterday, brick_before)
    # 反包阈值 = 昨日低点 + 2/3高度
    zddd = min(brick_yesterday, brick_before)
    fbwz = zddd + lzgd * 2 / 3

    # 满足2/3反包
    is_fanbao = brick_today > fbwz if lzgd > 0 else False

    return is_red and is_green_yesterday and is_fanbao


def detect_b1_today(klines: List[DailyData]) -> Dict:
    """
    B1建仓波检测（只检查最新这天）
    标准：J<13, 振幅<4%, 涨幅-2%~+1.8%, 缩量
    """
    result: dict[str, Any] = {
        'is_b1': False,
        'b1_j_value': 0.0,
        'b1_amplitude': 0.0,
        'b1_pct_chg': 0.0,
        'b1_volume_shrink': False,
        'b1_score': 0.0,
    }
    if len(klines) < 2:
        return result
    today = klines[-1]
    prev = klines[-2]
    _, _, j = calculate_kdj(klines)
    amplitude = (today.high - today.low) / prev.close * 100 if prev.close > 0 else 0
    pct = today.pct_chg
    vol_shrink = today.vol < prev.vol
    score = 0
    if j < 13: score += 1
    if amplitude < 4: score += 1
    if -2 <= pct <= 1.8: score += 1
    if vol_shrink: score += 1
    if score >= 3:
        result['is_b1'] = True
    result['b1_j_value'] = round(j, 2)
    result['b1_amplitude'] = round(amplitude, 2)
    result['b1_pct_chg'] = round(pct, 2)
    result['b1_volume_shrink'] = vol_shrink
    result['b1_score'] = score
    return result


def detect_b2_today(klines: List[DailyData]) -> Dict:
    """
    B2突破检测（只检查最新这天）
    标准：B1后5天内, 涨幅>=4%, 放量20%+, J<55
    """
    result: dict[str, Any] = {
        'is_b2': False,
        'b2_follows_b1': False,
        'b2_pct_chg': 0.0,
        'b2_j_value': 0.0,
        'b2_volume_up': False,
        'b2_score': 0.0,
    }
    if len(klines) < 10:
        return result
    today = klines[-1]
    prev = klines[-2]
    if not prev or prev.close <= 0:
        return result
    # 检查最近5天是否有B1痕迹
    has_recent_b1 = False
    for i in range(max(1, len(klines) - 5), len(klines)):
        _, _, j_check = calculate_kdj(klines[:i + 1])
        if j_check < 13:
            has_recent_b1 = True
            break
    _, _, j = calculate_kdj(klines)
    pct = today.pct_chg
    vol_up = today.vol > prev.vol * 1.2
    score = 0
    if has_recent_b1: score += 1
    if pct >= 4: score += 1
    if j < 55: score += 1
    if vol_up: score += 1
    if has_recent_b1 and pct >= 4 and score >= 3:
        result['is_b2'] = True
    result['b2_follows_b1'] = has_recent_b1
    result['b2_pct_chg'] = round(pct, 2)
    result['b2_j_value'] = round(j, 2)
    result['b2_volume_up'] = vol_up
    result['b2_score'] = score
    return result


def _build_brick_colors(brick_history: List[float]) -> List[int]:
    """将砖值序列转为红绿砖颜色列表：1=红砖(上涨)，-1=绿砖(下跌)。"""
    colors = []
    for i in range(1, len(brick_history)):
        colors.append(1 if brick_history[i] >= brick_history[i - 1] else -1)
    return colors


def _count_consecutive_bricks(colors: List[int]) -> Tuple[int, int]:
    """返回 (current_color, 从最新往前连续同色砖数)。"""
    current_color = colors[-1]
    count = 1
    for i in range(len(colors) - 2, -1, -1):
        if colors[i] == current_color:
            count += 1
        else:
            break
    return current_color, count


def _resolve_brick_action(colors: List[int], current_color: int, count: int) -> Tuple[bool, str, str]:
    """
    根据砖色和连续数返回 (is_flip_green, brick_action, brick_action_desc)。
    """
    # 1. 红砖翻绿（止损信号）
    if current_color == -1 and len(colors) >= 2 and colors[-2] == 1:
        return (
            True,
            '止损',
            f'红砖翻绿！立刻止损（连续红砖{count}块后翻绿）',
        )
    # 2. 红砖满4块 → 减仓
    if current_color == 1 and count >= 4:
        desc = '红砖已满4块，至少减仓一半' if count == 4 else f'红砖已延续{count}块，趋势延续中，但未减仓需警惕'
        return False, '减仓', desc
    # 3. 绿砖下跌 → 禁止抄底
    if current_color == -1:
        desc = (
            f'绿砖已连续{count}块，跌势可能接近尾声但仍禁止抄底'
            if count >= 4 else
            f'绿砖下跌中（{count}块），绝不抄底，先数4块'
        )
        return False, '禁止抄底', desc
    # 4. 红砖不足4块 → 持有
    if current_color == 1 and count < 4:
        return False, '持有', f'红砖上涨中（{count}块），继续持有'
    return False, '观望', '中性'


def detect_four_brick_system(klines: List[DailyData]) -> Dict:
    """
    四块砖交易体系检测

    通达信公式逻辑（与官方一致）：
    - 红砖 = 上涨动量（今日砖值 >= 昨日砖值）→ COLORRED
    - 绿砖 = 下跌动量（今日砖值 < 昨日砖值）→ COLOR00FF00

    规则：
    1. 红砖数满4块 → 减仓至少一半
    2. 红砖翻绿 → 立刻止损
    3. 绿砖下跌 → 绝不抄底，先数4块
    4. 买入后3天不涨 → 止损（DSZ铁律）
    """
    result = {
        'brick_consecutive': 0,      # 当前连续砖数
        'brick_action': '观望',      # 操作建议
        'brick_action_desc': '',     # 操作描述
        'is_brick_flip_green': False,  # 红砖刚翻绿（上涨转下跌）
    }

    if len(klines) < 10:
        result['brick_action_desc'] = '数据不足'
        return result

    # 计算历史砖值序列（至少需要8天才能开始算砖值）
    brick_history = []
    for i in range(8, len(klines) + 1):
        brick_history.append(calculate_brick_value(klines[:i]))

    if len(brick_history) < 3:
        result['brick_action_desc'] = '数据不足'
        return result

    # 计算红绿砖颜色序列
    colors = _build_brick_colors(brick_history)

    if not colors:
        result['brick_action_desc'] = '无砖型数据'
        return result

    # 从最新往前数连续同色砖
    current_color, count = _count_consecutive_bricks(colors)
    result['brick_consecutive'] = count

    # 规则判断 → 操作建议
    is_flip, action, desc = _resolve_brick_action(colors, current_color, count)
    result['is_brick_flip_green'] = is_flip
    result['brick_action'] = action
    result['brick_action_desc'] = desc
    return result
