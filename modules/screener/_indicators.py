"""
技术指标计算：MA / VolMA / KDJ / BBI / 完美图形
"""

from typing import List, Dict, Tuple


def calculate_ma(prices: List[float], period: int) -> float:
    """计算均线"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_vol_ma(vols: List[float], period: int) -> float:
    """计算量能均线"""
    if len(vols) < period:
        return 0
    return sum(vols[-period:]) / period


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """计算KDJ"""
    if len(klines) < period:
        return 50, 50, 50

    rsv_list = []
    for i in range(period - 1, len(klines)):
        low_list = [klines[j]['low'] for j in range(i - period + 1, i + 1)]
        high_list = [klines[j]['high'] for j in range(i - period + 1, i + 1)]
        low_min = min(low_list)
        high_max = max(high_list)

        if high_max == low_min:
            rsv = 50
        else:
            rsv = (klines[i]['close'] - low_min) / (high_max - low_min) * 100
        rsv_list.append(rsv)

    k = d = 50.0
    for rsv in rsv_list:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k

    j = 3 * k - 2 * d
    return round(k, 2), round(d, 2), round(j, 2)


def calculate_bbi(klines: List[Dict]) -> float:
    """计算BBI"""
    if len(klines) < 24:
        return 0
    closes = [k['close'] for k in klines]
    return round((calculate_ma(closes, 3) + calculate_ma(closes, 6) +
                 calculate_ma(closes, 12) + calculate_ma(closes, 24)) / 4, 2)


def is_perfect_pattern(klines: List[Dict]) -> Tuple[bool, List[str]]:
    """
    判断是否完美图形

    完美图形条件:
    1. BBI之上
    2. 缩量整理
    3. 均线多头（可选）
    4. 非高位
    """
    if len(klines) < 30:
        return False, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

    reasons = []
    warnings = []

    # 1. BBI之上
    if today['close'] > bbi:
        reasons.append("价格在BBI之上")
    else:
        warnings.append("价格在BBI下方")

    # 2. 缩量整理
    ma5_vol = calculate_vol_ma(vols, 5)
    today_vol = today['vol']
    if today_vol < ma5_vol * 0.7:
        reasons.append("缩量整理")
    elif today_vol > ma5_vol * 1.5:
        warnings.append("放量突破，需观察")

    # 3. 均线多头
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    if ma5 > ma10 > ma20:
        reasons.append("均线多头排列")
    elif ma5 < ma10:
        warnings.append("均线空头")

    # 4. 非高位（距历史高点跌幅充分）
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio > 0.3:
        reasons.append(f"相对高点回调{drop_ratio*100:.0f}%")
    elif drop_ratio < 0.1:
        warnings.append("接近历史高位")

    # 综合判断
    is_perfect = len(reasons) >= 2 and len(warnings) == 0

    return is_perfect, reasons
