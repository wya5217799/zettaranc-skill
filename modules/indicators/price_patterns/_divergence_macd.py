"""
MACD 信号与背离检测模块
"""

from typing import List, Dict, Any, Tuple

from ..core import DailyData


def detect_divergence(klines: List[DailyData], dif_list: List[float]) -> Dict:
    """
    顶底背离系统化检测（基于语料标准）

    顶背离：价格创新高但DIF不创新高 → 趋势衰竭，见顶减仓
    底背离：价格创新低但DIF不创新低 → 反转在即，底部建仓

    要求：
    - 对比窗口：最近60个交易日的极值区间
    - 价格容忍度：接近极值1%-2%即视为"同一水平"
    - DIF衰减：DIF未突破前值的90%(顶)或未跌破前值的110%(底)
    """
    result = {
        'is_top_divergence': False,
        'is_bottom_divergence': False,
    }

    if len(klines) < 60 or len(dif_list) < 30:
        return result

    closes = [k.close for k in klines]
    today_close = closes[-1]

    # ====== 顶背离检测 ======
    # 找最近60天内的最高收盘价窗口（排除最后5天，避免与当前比较）
    window_start = max(0, len(closes) - 60)
    window_end = max(0, len(closes) - 10)
    if window_end <= window_start:
        window_end = len(closes) - 5

    if window_end > window_start:
        max_close = max(closes[window_start:window_end])

        # 对应窗口的DIF最大值
        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            max_dif = max(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最高，但DIF明显低于前高
            price_near_high = today_close >= max_close * 0.98
            dif_weaker = dif_list[-1] < max_dif * 0.9

            if price_near_high and dif_weaker and max_dif > 0:
                result['is_top_divergence'] = True

    # ====== 底背离检测 ======
    if window_end > window_start:
        min_close = min(closes[window_start:window_end])

        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            min_dif = min(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最低，但DIF明显高于前低
            price_near_low = today_close <= min_close * 1.02
            dif_stronger = dif_list[-1] > min_dif * 1.1

            if price_near_low and dif_stronger and min_dif < 0:
                result['is_bottom_divergence'] = True

    return result


def _count_recent_crosses(
    dif_list: List[float],
    dea_list: List[float],
) -> Tuple[int, int]:
    """统计最近3天内的金叉/死叉次数，供 detect_macd_signals 使用。"""
    recent_gold = 0
    recent_dead = 0
    offset = len(dif_list) - len(dea_list)
    for i in range(max(0, len(dif_list) - 4), len(dif_list) - 1):
        dei = i - offset
        if 0 <= dei < len(dea_list) and dei + 1 < len(dea_list):
            prev_dei = dei - 1 if dei > 0 else 0
            if dif_list[i] > dea_list[dei] and dif_list[i - 1] <= dea_list[prev_dei]:
                recent_gold += 1
            if dif_list[i] < dea_list[dei] and dif_list[i - 1] >= dea_list[prev_dei]:
                recent_dead += 1
    return recent_gold, recent_dead


def detect_macd_signals(klines: List[DailyData], dif_list: List[float],
                        dea_list: List[float], macd_list: List[float]) -> Dict[str, Any]:
    """
    根据 Z哥 语料检测 MACD 信号

    三大用法:
    1. DIF 上下穿 0 轴 — 判多空区间
    2. 顶/底背离 — 判趋势终结
    3. 金叉空 + 死叉多 — 判陷阱
    """
    signals = {
        'is_dif_positive': False,
        'is_dif_cross_zero': False,
        'is_dif_cross_zero_down': False,
        'is_gold_cross': False,
        'is_dead_cross': False,
        'is_gold_fake': False,
        'is_dead_fake': False,
        'is_top_divergence': False,
        'is_bottom_divergence': False,
        'macd_veto': False,
    }

    if len(dif_list) < 2 or len(dea_list) < 1:
        return signals

    dif_today = dif_list[-1]
    dif_yesterday = dif_list[-2] if len(dif_list) >= 2 else 0
    dea_today = dea_list[-1]
    dea_yesterday = dea_list[-2] if len(dea_list) >= 2 else 0

    # === 用法 1: DIF 0 轴判多空 ===
    signals['is_dif_positive'] = dif_today > 0

    # DIF 上穿 0 轴
    signals['is_dif_cross_zero'] = dif_yesterday <= 0 and dif_today > 0
    # DIF 下穿 0 轴
    signals['is_dif_cross_zero_down'] = dif_yesterday >= 0 and dif_today < 0

    # === 金叉/死叉 ===
    if len(dif_list) >= 3 and len(dea_list) >= 2:
        signals['is_gold_cross'] = dif_yesterday <= dea_yesterday and dif_today > dea_today
        signals['is_dead_cross'] = dif_yesterday >= dea_yesterday and dif_today < dea_today

    # === 用法 3: 金叉空 + 死叉多（多等一天）===
    if len(dif_list) >= 5 and len(dea_list) >= 3:
        recent_gold, recent_dead = _count_recent_crosses(dif_list, dea_list)

        # 金叉空：刚金叉又马上死叉
        if signals['is_dead_cross'] and recent_gold >= 1:
            signals['is_gold_fake'] = True

        # 死叉多：刚死叉又马上金叉
        if signals['is_gold_cross'] and recent_dead >= 1:
            signals['is_dead_fake'] = True

    # === 用法 2: 顶底背离（系统化检测）===
    div = detect_divergence(klines, dif_list)
    signals['is_top_divergence'] = div['is_top_divergence']
    signals['is_bottom_divergence'] = div['is_bottom_divergence']

    # === 一票否决权 ===
    # DIF < 0 + 没有底背离 → 一票否决
    if dif_today < 0 and not signals['is_bottom_divergence']:
        signals['macd_veto'] = True

    return signals
