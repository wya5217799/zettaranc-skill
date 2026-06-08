"""
股票评分：B1 / 趋势 / 量价 / 风险 / 综合 / P2 指标加权
"""

from typing import List, Dict, Optional, Tuple

from ._models import StockScore
from ._indicators import (
    calculate_ma, calculate_vol_ma, calculate_kdj,
    calculate_bbi, is_perfect_pattern,
)
from ._data import get_db_connection, get_recent_klines


def score_b1_opportunity(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估B1买点机会

    返回: (评分0-100, 原因列表)
    """
    if len(klines) < 20:
        return 0, ["数据不足"]

    today = klines[-1]
    k, d, j = calculate_kdj(klines)
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

    score = 0
    reasons = []

    # J值评分（核心）
    if j < -15:
        score += 35
        reasons.append(f"J值极低: {j:.2f}")
    elif j < -10:
        score += 25
        reasons.append(f"J值低位: {j:.2f}")
    elif j < 0:
        score += 15
        reasons.append(f"J值: {j:.2f}")

    # 缩量回调加分
    if today['vol'] < calculate_vol_ma(vols, 5) * 0.6:
        score += 20
        reasons.append("缩量回调")

    # BBI下方（低位）
    if today['close'] < bbi:
        score += 15
        reasons.append("BBI下方低位")

    # 价格在合理区间
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    if ma20 < today['close'] < ma60:
        score += 15
        reasons.append("中期均线区间")

    # 风险提示
    if j > 0:
        score -= 10
    if today['close'] > bbi * 1.05:
        score -= 15

    return max(0, min(100, score)), reasons


def score_trend(klines: List[Dict]) -> Tuple[float, str]:
    """
    评估趋势

    返回: (评分0-100, 趋势方向)
    """
    if len(klines) < 20:
        return 50, "震荡"

    closes = [k['close'] for k in klines]
    today = klines[-1]
    bbi = calculate_bbi(klines)

    ma5 = calculate_ma(closes, 5)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)

    # 趋势判断
    if ma5 > ma20 > ma60 and today['close'] > bbi:
        direction = "上升"
        score = 80 if today['pct_chg'] > 0 else 70
    elif ma5 < ma20 < ma60 and today['close'] < bbi:
        direction = "下降"
        score = 30
    else:
        direction = "震荡"
        score = 50

    # 短期动能
    if len(klines) >= 5:
        recent_pct = sum(k['pct_chg'] for k in klines[-5:])
        if recent_pct > 10:
            score += 10
        elif recent_pct < -10:
            score -= 10

    return max(0, min(100, score)), direction


def score_volume_pattern(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估量价形态
    """
    if len(klines) < 10:
        return 50, ["数据不足"]

    today = klines[-1]
    vols = [k['vol'] for k in klines]
    vol_ma5 = calculate_vol_ma(vols, 5)

    score = 50
    reasons = []

    # 量比
    vol_ratio = today['vol'] / vol_ma5
    if vol_ratio >= 2:
        score += 20
        reasons.append(f"倍量(量比{vol_ratio:.1f}x)")
    elif vol_ratio >= 1.5:
        score += 10
        reasons.append("放量")
    elif vol_ratio <= 0.5:
        score += 10
        reasons.append("缩量")
    else:
        score -= 5
        reasons.append("量能正常")

    # 涨跌配合
    if today['pct_chg'] > 3 and vol_ratio > 1.2:
        score += 15
        reasons.append("价涨量增(攻击形态)")
    elif today['pct_chg'] < -3 and vol_ratio > 1.2:
        score -= 15
        reasons.append("价跌量增(出货嫌疑)")

    return max(0, min(100, score)), reasons


def score_risk(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估风险
    """
    if len(klines) < 20:
        return 50, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)

    score = 100  # 初始100分，越高越安全
    warnings = []

    # 高位风险
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio < 0.1:
        score -= 30
        warnings.append("接近历史高位")
    elif drop_ratio < 0.2:
        score -= 15
        warnings.append("相对高位")

    # 跌破BBI风险
    if today['close'] < bbi:
        score -= 20
        warnings.append("跌破BBI")

    # 放量阴线风险
    for i in range(min(5, len(klines)-1)):
        k = klines[-(i+1)]
        prev = klines[-(i+2)] if i < len(klines)-2 else None
        if prev and k['close'] < prev['close'] and k['vol'] > prev['vol'] * 1.5:
            score -= 10
            warnings.append("近期有放量阴线")
            break

    # 连续下跌
    recent_3_drop = sum(1 for k in klines[-3:] if k['close'] < k['prev_close'])
    if recent_3_drop >= 3:
        score -= 15
        warnings.append("连续3天下跌")

    return max(0, min(100, score)), warnings


def _apply_p2_indicators(
    klines: List[Dict],
    b1_reasons: List[str],
    risk_warnings: List[str],
    risk_score: float,
) -> Tuple[str, str, List[str], List[str], float]:
    """
    计算 P2 三波理论 + 麒麟会指标，更新 b1_reasons / risk_warnings / risk_score。
    返回: (wave_stage, kirin_stage, b1_reasons, risk_warnings, risk_score)
    """
    wave_stage = "未知"
    kirin_stage = "未知"
    try:
        from modules.indicators import DailyData, detect_three_waves, detect_kirin_stage
        daily_klines = []
        for i, k in enumerate(klines):
            prev_close = klines[i-1]['close'] if i > 0 else k['close']
            daily_klines.append(DailyData(
                ts_code=k['ts_code'],
                trade_date=k['trade_date'],
                open=k['open'],
                high=k['high'],
                low=k['low'],
                close=k['close'],
                vol=k['vol'],
                amount=k.get('amount', k['close'] * k['vol']),
                pct_chg=k.get('pct_chg', 0),
                prev_close=prev_close,
            ))
        wave = detect_three_waves(daily_klines)
        wave_stage = wave['wave']
        if wave_stage == '建仓波' and wave['confidence'] >= 0.5:
            b1_reasons.append(f"三波·建仓波(conf={wave['confidence']})")
        elif wave_stage == '拉升波':
            b1_reasons.append(f"三波·拉升波(conf={wave['confidence']})→等回调")
        elif wave_stage == '冲刺波':
            risk_warnings.append(f"三波·冲刺波(conf={wave['confidence']})→不看")
            risk_score = max(0, risk_score - 20)

        kirin = detect_kirin_stage(daily_klines)
        kirin_stage = kirin['stage']
        if kirin_stage == '吸筹' and kirin['confidence'] >= 0.5:
            b1_reasons.append(f"麒麟会·吸筹({kirin['sub_type']}, conf={kirin['confidence']})")
        elif kirin_stage == '拉升':
            b1_reasons.append(f"麒麟会·拉升({kirin['sub_type']})→不追")
        elif kirin_stage == '派发':
            risk_warnings.append(f"麒麟会·派发({kirin['sub_type']})→准备走人")
            risk_score = max(0, risk_score - 30)
        elif kirin_stage == '回落':
            risk_warnings.append(f"麒麟会·回落({kirin['sub_type']})→不抄底")
            risk_score = max(0, risk_score - 15)
    except Exception:
        pass
    return wave_stage, kirin_stage, b1_reasons, risk_warnings, risk_score


def _adjust_total_score(total_score: float, wave_stage: str, kirin_stage: str) -> float:
    """三波/麒麟会加权调整综合评分。"""
    if wave_stage == '建仓波':
        return min(100, total_score * 1.05)
    if wave_stage == '冲刺波' or kirin_stage == '派发':
        return max(0, total_score * 0.7)
    if kirin_stage == '吸筹':
        return min(100, total_score * 1.08)
    return total_score


def analyze_stock(ts_code: str, klines: Optional[List[Dict]] = None) -> StockScore:
    """
    综合评分单只股票
    """
    if klines is None:
        klines = get_recent_klines(ts_code)

    if not klines:
        return StockScore(ts_code=ts_code)

    # 获取股票名称
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stock_basic WHERE ts_code = ?", (ts_code,))
    row = cursor.fetchone()
    name = row['name'] if row else ts_code
    conn.close()

    # 计算各项评分
    b1_score, b1_reasons = score_b1_opportunity(klines)
    trend_score, trend_dir = score_trend(klines)
    volume_score, volume_reasons = score_volume_pattern(klines)
    risk_score, risk_warnings = score_risk(klines)

    # ========== P2 指标：三波理论 + 麒麟会 ==========
    wave_stage, kirin_stage, b1_reasons, risk_warnings, risk_score = _apply_p2_indicators(
        klines, b1_reasons, risk_warnings, risk_score
    )

    # 综合评分（加权平均）
    # B1机会 30% + 趋势 25% + 量价 25% + 风险 20%
    total_score = b1_score * 0.3 + trend_score * 0.25 + volume_score * 0.25 + risk_score * 0.2

    # 完美图形额外加分
    is_perfect, perfect_reasons = is_perfect_pattern(klines)
    if is_perfect:
        total_score = min(100, total_score * 1.1)
        b1_reasons.extend(perfect_reasons)

    # 三波/麒麟会加权调整
    total_score = _adjust_total_score(total_score, wave_stage, kirin_stage)

    score = StockScore(
        ts_code=ts_code,
        name=name,
        score=round(total_score, 1),
        b1_score=round(b1_score, 1),
        trend_score=round(trend_score, 1),
        volume_score=round(volume_score, 1),
        risk_score=round(risk_score, 1),
        reasons=b1_reasons + volume_reasons,
        warnings=risk_warnings
    )

    return score


# ==================== 并行化 Worker ====================

def _analyze_worker(ts_code: str) -> Optional[Tuple[str, List[Dict], StockScore]]:
    """
    并行 worker：评分单只股票
    必须在模块顶层定义，以便 ProcessPoolExecutor 可以 pickle
    返回: (ts_code, klines, score) 或 None
    """
    klines = get_recent_klines(ts_code, 60)
    if not klines or len(klines) < 30:
        return None
    score = analyze_stock(ts_code, klines)
    return ts_code, klines, score
