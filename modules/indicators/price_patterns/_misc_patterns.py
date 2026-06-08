"""
关键K线、图形形态、呼吸结构、高级战法检测模块
"""

from typing import List, Dict, Any

from ..core import (
    DailyData, calculate_ma,
)
from ._calculators import calculate_zg_white, calculate_dg_yellow


def detect_key_k(klines: List[DailyData], lookback: int = 60) -> List[Dict]:
    """
    关键K检测（位置 + 放量 + 长阳/长阴），扫描最近lookback天
    找出那2-3根真正在指挥走势的关键K
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0

        is_big_body = body_pct >= 3
        # 大阳线(>=7%)或涨停时放宽量比要求，涨停缩量突破也认可
        vol_threshold = 1.1 if body_pct >= 7 else 1.3
        is_high_vol = vol_ratio >= vol_threshold

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_high = max(k.high for k in scan[pos_start:i])
            recent_low = min(k.low for k in scan[pos_start:i])
            dist_high = (day.high - recent_high) / recent_high
            dist_low = (recent_low - day.low) / recent_low if recent_low > 0 else 0
            at_key = (dist_high >= -0.02 and dist_high <= 0.15) or (dist_low >= -0.02 and dist_low <= 0.15)
        else:
            at_key = False

        if is_big_body and is_high_vol and at_key:
            results.append({
                'date': day.trade_date,
                'close': day.close,
                'pct': day.pct_chg,
                'type': '反转' if day.close > day.open else '衰竭',
                'body_pct': round(body_pct, 1),
                'vol_ratio': round(vol_ratio, 1),
                'is_latest': (i == n - 1),
            })

    return results


def detect_violence_k(klines: List[DailyData], lookback: int = 60) -> List[Dict]:
    """
    暴力K检测（底部 + 突兀 + 倍量），扫描最近lookback天
    关键K的满配版
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_low = min(k.low for k in scan[pos_start:i])
            at_bottom = day.low <= recent_low * 1.05
        else:
            at_bottom = False

        body_start = max(0, i - 5)
        prev_bodies = []
        for j in range(body_start, i):
            p = scan[j - 1] if j > 0 else None
            if p and p.close > 0:
                prev_bodies.append(abs(scan[j].close - scan[j].open) / p.close * 100)
        avg_body = sum(prev_bodies) / len(prev_bodies) if prev_bodies else 0
        is_abrupt = body_pct > avg_body * 2 and body_pct >= 5

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0
        is_double_vol = vol_ratio >= 2

        if at_bottom and is_abrupt and is_double_vol:
            results.append({
                'date': day.trade_date,
                'close': day.close,
                'pct': day.pct_chg,
                'type': '大暴力' if vol_ratio >= 3 else '小暴力',
                'body_pct': round(body_pct, 1),
                'vol_ratio': round(vol_ratio, 1),
                'is_latest': (i == n - 1),
            })

    return results


def check_two_30_rule(klines: List[DailyData]) -> Dict:
    """
    两个30%原则检查（B1筛选）
    1. B1涨幅约30%
    2. 累计换手率不超过30%
    """
    result: dict[str, Any] = {
        'b1_rally_pct': 0.0,
        'b1_turnover': 0.0,
        'b1_pass_30': False,
    }
    if len(klines) < 10:
        return result
    # 找最近30天的最低点作为B1起点
    lookback = min(30, len(klines))
    lows = [(klines[-lookback + i].low, klines[-lookback + i].close) for i in range(lookback)]
    min_price, min_close = min(lows, key=lambda x: x[0])
    today_close = klines[-1].close
    rally_pct = (today_close - min_close) / min_close * 100 if min_close > 0 else 0
    # 估算累计换手率（简化：累加每日vol/流通股本，用vol近似）
    # 用更简单的方式：涨幅在25%-35%之间算通过
    result['b1_rally_pct'] = round(rally_pct, 2)
    result['b1_pass_30'] = 25 <= rally_pct <= 40
    return result


def detect_nana_chart(klines: List[DailyData]) -> Dict:
    """
    娜娜图检测：完美建仓形态
    条件：股价新高但阳线缩量，次高点阴线也缩量
    """
    result = {'is_nana': False}
    if len(klines) < 20:
        return result
    n = len(klines)
    # 找最近高点区域
    highs = [k.high for k in klines]
    peak_idx = n - 1
    for i in range(n - 2, max(0, n - 30), -1):
        if highs[i] >= highs[peak_idx]:
            peak_idx = i
    # 从峰值往前找第二高
    second_peak = None
    for i in range(peak_idx - 2, max(0, peak_idx - 25), -1):
        if klines[i].high < klines[peak_idx].high * 0.98:
            second_peak = i
            break
    if second_peak is None or peak_idx < 5:
        return result
    # 检查峰值区域是否缩量
    peak_vol = klines[peak_idx].vol
    prev5_avg = sum(k.vol for k in klines[max(0,peak_idx-5):peak_idx]) / min(5, peak_idx)
    vol_shrink_at_peak = peak_vol < prev5_avg * 0.8 if prev5_avg > 0 else False
    # 次高点缩量
    second_vol = klines[second_peak].vol
    sec_prev5 = sum(k.vol for k in klines[max(0,second_peak-5):second_peak]) / min(5, second_peak)
    vol_shrink_second = second_vol < sec_prev5 * 0.8 if sec_prev5 > 0 else False
    # 底部堆量：找低点区域量是否明显大于峰值区域
    low_idx = min(range(max(0, second_peak-10), second_peak), key=lambda i: klines[i].low)
    bottom_vol = klines[low_idx].vol
    if vol_shrink_at_peak and vol_shrink_second and bottom_vol > peak_vol * 0.5:
        result['is_nana'] = True
    return result


def detect_golden_bowl(klines: List[DailyData]) -> Dict:
    """
    黄金碗检测：价格在白线( zg_white )和黄线( dg_yellow )之间
    条件：白线>黄线(多头排列) + 价格落入碗内
    """
    result: dict[str, Any] = {'is_in_bowl': False, 'bowl_upper': 0.0, 'bowl_lower': 0.0}
    if len(klines) < 120:
        return result
    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    if white <= 0 or yellow <= 0:
        return result
    result['bowl_upper'] = round(white, 2)
    result['bowl_lower'] = round(yellow, 2)
    today_close = klines[-1].close
    # 白线>黄线且价格在碗内
    if white > yellow and yellow <= today_close <= white:
        result['is_in_bowl'] = True
    return result


def _classify_vol_price_phase(day: DailyData, prev: DailyData) -> str:
    """将单根K线分类为 'exhale'（放量涨）/ 'inhale'（缩量跌）/ 'other'。"""
    if prev.vol <= 0:
        return 'other'
    vol_ratio = day.vol / prev.vol
    if day.pct_chg > 0 and vol_ratio > 1:
        return 'exhale'  # 放量涨=呼气
    if day.pct_chg < 0 and vol_ratio < 1:
        return 'inhale'  # 缩量跌=吸气
    return 'other'


def detect_breathing_structure(klines: List[DailyData]) -> Dict:
    """
    呼吸结构检测：放量涨->缩量跌->放量涨 的N型节奏
    """
    result = {'breath_phase': '', 'breath_n_type': False}
    if len(klines) < 10:
        return result
    n = len(klines)
    # 分析最近5-7天的量价节奏
    phases = []
    for i in range(max(0, n - 7), n):
        prev = klines[i - 1] if i > 0 else None
        if not prev:
            continue
        phases.append(_classify_vol_price_phase(klines[i], prev))
    # 判断当前阶段
    if len(phases) >= 2:
        last = phases[-1]
        result['breath_phase'] = last if last in ('exhale', 'inhale') else 'none'
    # N型结构：最近3个低点依次抬高
    if n >= 10:
        lows = [klines[i].low for i in range(n - 10, n, 3)]
        if len(lows) >= 3 and lows[-1] > lows[-2] > lows[-3]:
            result['breath_n_type'] = True
    return result


def detect_sb1(klines: List[DailyData]) -> Dict:
    """
    SB1假摔检测：B1后跌破前低再迅速收回
    条件：1)跌破前低 2)次日反包收回 3)收回放量
    """
    result = {'is_sb1': False}
    if len(klines) < 6:
        return result
    n = len(klines)
    yesterday = klines[-2]
    # 前天是假摔日
    if len(klines) >= 3:
        fake_drop = klines[-3]
        prev_low = min(k.low for k in klines[-8:-3]) if n >= 8 else klines[-4].low
        # 1) 跌破前低
        broken_low = fake_drop.low < prev_low
        # 2) 次日反包收回
        recovered = yesterday.close > prev_low and yesterday.pct_chg > 2
        # 3) 反包放量
        vol_up = yesterday.vol > fake_drop.vol * 1.2
        if broken_low and recovered and vol_up:
            result['is_sb1'] = True
    return result


def detect_b3(klines: List[DailyData]) -> Dict:
    """
    B3买点检测：B2后缩量回踩不破B2低点
    条件：1) 前面有B2(大涨>=4%) 2) 缩量小阳/十字星 3) 不破B2低点
    """
    result = {'is_b3': False}
    if len(klines) < 15:
        return result
    n = len(klines)
    today = klines[-1]
    # 往前找B2(大涨>=4%的阳线)
    b2_idx = None
    for i in range(n - 2, max(0, n - 15), -1):
        if klines[i].pct_chg >= 4 and klines[i].close > klines[i].open:
            b2_idx = i
            break
    if b2_idx is None:
        return result
    b2_low = klines[b2_idx].low
    # B2后缩量小阳线
    days_after = n - 1 - b2_idx
    if 2 <= days_after <= 5:
        today_vol_ratio = today.vol / klines[b2_idx].vol if klines[b2_idx].vol > 0 else 0
        not_break_low = today.low >= b2_low * 0.98
        small_candle = abs(today.pct_chg) < 3
        if today_vol_ratio < 0.8 and not_break_low and small_candle:
            result['is_b3'] = True
    return result


def detect_zaihou_chongjian(klines: List[DailyData]) -> Dict:
    """
    灾后重建检测 —— 放量金叉后缩量回踩黄线

    来源：advanced-patterns.md
    定义：放量金叉后缩量回踩黄线，交易价值最大，是最后拉升前的震仓动作。

    条件：
    1. 前期有放量上涨（涨幅 > 5%，量 > 前5日均量 × 1.5）
    2. 近期缩量回调（量 < 放量日量的 60%）
    3. 价格回踩黄线（大哥线 / 4参数BBI变体）附近（±2%）
    4. 黄线趋势向上

    Args:
        klines: K线数据（至少60根）

    Returns:
        {'is_rebuild': bool, 'confidence': float, 'desc': str}
    """
    if len(klines) < 60:
        return {'is_rebuild': False}

    today = klines[-1]

    # 计算黄线（4参数BBI变体）
    closes = [k.close for k in klines]
    ma3 = calculate_ma(closes, 3)
    ma6 = calculate_ma(closes, 6)
    ma12 = calculate_ma(closes, 12)
    ma24 = calculate_ma(closes, 24)
    yellow_line = (ma3 + ma6 + ma12 + ma24) / 4

    # 黄线趋势：近5天黄线 vs 近10天黄线
    yellow_5 = (calculate_ma(closes[-5:], 3) + calculate_ma(closes[-5:], 6) +
                calculate_ma(closes[-5:], 12) + calculate_ma(closes[-5:], 24)) / 4
    yellow_10 = (calculate_ma(closes[-10:], 3) + calculate_ma(closes[-10:], 6) +
                 calculate_ma(closes[-10:], 12) + calculate_ma(closes[-10:], 24)) / 4
    yellow_up = yellow_5 > yellow_10

    # 查找近期放量上涨日（近15天内）
    recent_15 = klines[-15:]
    fangliang_day = None
    for i, k in enumerate(recent_15):
        if i == 0:
            continue
        prev_5_avg = sum(kl.vol for kl in recent_15[max(0, i-5):i]) / 5
        if k.pct_chg > 5 and k.vol > prev_5_avg * 1.5:
            fangliang_day = k
            break

    if fangliang_day is None:
        return {'is_rebuild': False}

    # 缩量条件：今天量 < 放量日量的 60%
    is_suoliang = today.vol < fangliang_day.vol * 0.6

    # 回踩黄线：收盘价在黄线 ±2% 范围内
    near_yellow = abs(today.close - yellow_line) / yellow_line < 0.02 if yellow_line > 0 else False

    if is_suoliang and near_yellow and yellow_up:
        return {
            'is_rebuild': True,
            'confidence': 0.85,
            'yellow_line': round(yellow_line, 2),
            'fangliang_price': round(fangliang_day.close, 2),
            'desc': f'灾后重建：放量({fangliang_day.close:.2f})后缩量回踩黄线({yellow_line:.2f})'
        }

    return {'is_rebuild': False}


def detect_yueyueyushi(klines: List[DailyData]) -> Dict:
    """
    跃跃欲试检测 —— 横盘期间放巨大量三次

    来源：advanced-patterns.md
    定义：横盘期间放巨大量，红长绿短、红肥绿瘦，出现至少三次后越往后突破概率越大。
    前提：仅限牛市、未出货的赛赛图。"横有多长竖有多高"。

    条件：
    1. 近20天振幅 < 15%（横盘）
    2. 近20天出现至少3次巨量（量 > 前10日均量 × 2）
    3. 巨量日多为阳线（红肥绿瘦）
    4. 当前未处于明显高位（距20日高点 < 10% 可接受）

    Args:
        klines: K线数据（至少30根）

    Returns:
        {'is_ready': bool, 'count': int, 'confidence': float, 'desc': str}
    """
    if len(klines) < 30:
        return {'is_ready': False}

    recent_20 = klines[-20:]
    high_20 = max(k.high for k in recent_20)
    low_20 = min(k.low for k in recent_20)
    amplitude = (high_20 - low_20) / low_20 if low_20 > 0 else 0

    # 横盘条件
    if amplitude > 0.15:
        return {'is_ready': False}

    # 计算近10日均量
    vols_10 = [k.vol for k in klines[-10:]]
    avg_vol_10 = sum(vols_10) / len(vols_10)

    # 统计巨量次数（量 > 前10日均量 × 2）
    juliang_count = 0
    yang_count = 0
    for k in recent_20:
        if k.vol > avg_vol_10 * 2:
            juliang_count += 1
            if k.close > k.open:
                yang_count += 1

    # 至少3次巨量，且阳线占比 > 50%
    if juliang_count >= 3 and yang_count / juliang_count > 0.5:
        confidence = 0.70 + 0.05 * min(juliang_count - 3, 3)  # 每多一次+5%，上限85%
        return {
            'is_ready': True,
            'count': juliang_count,
            'yang_ratio': round(yang_count / juliang_count, 2),
            'confidence': round(confidence, 2),
            'desc': f'跃跃欲试：横盘振幅{amplitude*100:.0f}%，{juliang_count}次巨量，阳线占比{yang_count/juliang_count*100:.0f}%'
        }

    return {'is_ready': False}


def detect_key_candle(klines: List[DailyData]) -> Dict:
    """
    关键 K 检测 —— 走势中管理其他 K 线的关键位置放量长中阳/阴

    来源：key-candles.md
    核心价值：
    1. 判断趋势反转（80分含金量）：下跌→上涨、横盘→上涨等
    2. 判断走势衰竭（20分含金量）：卖盘枯竭/买盘枯竭

    关键K条件：
    1. 关键位置（突破前高、跌破前低、平台边缘）
    2. 放量（量 > 前10日均量 × 1.5）
    3. 实体够大（|收-开| / (高-低) > 0.6）
    4. 阳线 close > open，阴线 close < open

    返回最近一根关键K的信息和趋势转换判断。

    Args:
        klines: K线数据（至少20根）

    Returns:
        {'is_key': bool, 'direction': str, 'type': str, 'confidence': float}
    """
    if len(klines) < 20:
        return {'is_key': False}

    today = klines[-1]
    recent_10 = klines[-10:]
    recent_20 = klines[-20:]

    # 实体比例
    body = abs(today.close - today.open)
    range_ = today.high - today.low
    body_ratio = body / range_ if range_ > 0 else 0

    # 放量
    avg_vol_10 = sum(k.vol for k in recent_10) / len(recent_10)
    is_fangliang = today.vol > avg_vol_10 * 1.5

    # 实体够大
    is_big_body = body_ratio > 0.6

    if not is_fangliang or not is_big_body:
        return {'is_key': False}

    # 判断关键位置
    high_20 = max(k.high for k in recent_20[:-1])  # 排除今天
    low_20 = min(k.low for k in recent_20[:-1])
    is_break_high = today.high > high_20 * 1.01  # 突破前高1%
    is_break_low = today.low < low_20 * 0.99   # 跌破前低1%

    # 判断方向
    is_yang = today.close > today.open
    is_yin = today.close < today.open

    result: dict[str, Any] = {'is_key': True, 'body_ratio': round(body_ratio, 2)}

    if is_yang and is_break_high:
        result['direction'] = '向上突破'
        result['type'] = '关键阳突破'
        result['confidence'] = 0.90
    elif is_yin and is_break_low:
        result['direction'] = '向下破位'
        result['type'] = '关键阴破位'
        result['confidence'] = 0.90
    elif is_yang:
        result['direction'] = '底部/回调阳'
        result['type'] = '关键阳'
        result['confidence'] = 0.75
    elif is_yin:
        result['direction'] = '顶部/滞涨阴'
        result['type'] = '关键阴'
        result['confidence'] = 0.75
    else:
        return {'is_key': False}

    return result
