"""
价格模式基础计算模块 — 供其他子模块导入的共享低级函数
"""

from typing import List, Tuple

from ..core import (
    DailyData, calculate_ma, calculate_ema,
)


def calculate_zg_white(klines: List[DailyData]) -> float:
    """
    计算 Z哥白线 = EMA(EMA(C,10),10)

    双重平滑后的短期动能线
    """
    if len(klines) < 10:
        return 0
    closes = [k.close for k in klines]
    ema1 = calculate_ema(closes, 10)
    # 再次平滑：用前10天数据计算第二次EMA
    if len(klines) < 19:
        return ema1
    recent_10 = closes[-10:]
    ema2 = calculate_ema(recent_10, 10)
    return round(ema2, 2)


def calculate_dg_yellow(klines: List[DailyData]) -> float:
    """
    计算 大哥线 = (MA14 + MA28 + MA57 + MA114) / 4

    多空生命线，长期均线系统
    """
    if len(klines) < 114:
        return 0
    closes = [k.close for k in klines]
    ma14 = calculate_ma(closes, 14)
    ma28 = calculate_ma(closes, 28)
    ma57 = calculate_ma(closes, 57)
    ma114 = calculate_ma(closes, 114)
    return round((ma14 + ma28 + ma57 + ma114) / 4, 2)


def calculate_rsl(klines: List[DailyData], period: int) -> float:
    """
    计算 RSL 相对强度定位（通达信标准公式）

    100*(C-LLV(L,N))/(HHV(C,N)-LLV(L,N))
    """
    if len(klines) < period:
        return 50

    recent = klines[-period:]
    lows = [k.low for k in recent]
    closes = [k.close for k in recent]
    current_close = klines[-1].close

    llv = min(lows)
    hhv = max(closes)  # 通达信用 HHV(CLOSE)，不是 HHV(HIGH)

    if hhv == llv:
        return 50

    rsl = (current_close - llv) / (hhv - llv) * 100
    return round(rsl, 2)


def _build_dm_tr_series(
    klines: List[DailyData],
) -> Tuple[List[float], List[float], List[float]]:
    """
    单次遍历计算 DMI+ 列表、DMI- 列表、TR 列表。
    供 calculate_dmi 使用。
    """
    dm_plus_list: List[float] = []
    dm_minus_list: List[float] = []
    tr_list: List[float] = []
    for i in range(1, len(klines)):
        high_diff = klines[i].high - klines[i - 1].high
        low_diff = klines[i - 1].low - klines[i].low
        dm_plus_list.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        dm_minus_list.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)
        high = klines[i].high
        low = klines[i].low
        prev_close = klines[i - 1].close
        tr_list.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return dm_plus_list, dm_minus_list, tr_list


def _calc_adx(
    dm_plus_list: List[float],
    dm_minus_list: List[float],
    tr_ma: float,
    period: int,
) -> float:
    """根据 DM 序列和 TR 均值计算 ADX 值。"""
    dx_list = []
    for i in range(period - 1, len(dm_plus_list)):
        di_plus = sum(dm_plus_list[i - period + 1:i + 1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        di_minus = sum(dm_minus_list[i - period + 1:i + 1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
        dx_list.append(dx)
    if not dx_list:
        return 0.0
    return sum(dx_list[-period:]) / period if len(dx_list) >= period else sum(dx_list) / len(dx_list)


def calculate_dmi(klines: List[DailyData], period: int = 14) -> Tuple[float, float, float]:
    """
    计算 DMI 趋向指标

    通达信公式:
    DMI: (MTM-MTM的N日简单移动平均) / (MTM的绝对值的N日简单移动平均) * 100
    MTM = CLOSE - REF(CLOSE,1)

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        (DMI+, DMI-, ADX)
    """
    if len(klines) < period + 1:
        return 0, 0, 0

    dm_plus_list, dm_minus_list, tr_list = _build_dm_tr_series(klines)

    if len(dm_plus_list) < period or len(tr_list) < period:
        return 0, 0, 0

    dm_plus_ma = sum(dm_plus_list[-period:]) / period
    dm_minus_ma = sum(dm_minus_list[-period:]) / period
    tr_ma = sum(tr_list[-period:]) / period

    if tr_ma == 0:
        return 0, 0, 0

    dmi_plus = dm_plus_ma / tr_ma * 100
    dmi_minus = dm_minus_ma / tr_ma * 100

    adx = _calc_adx(dm_plus_list, dm_minus_list, tr_ma, period)

    return round(dmi_plus, 2), round(dmi_minus, 2), round(adx, 2)
