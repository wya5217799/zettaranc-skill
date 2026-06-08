"""
选股过滤器：高级战法检测 + P2 指标策略 + 综合筛选
"""

from typing import List, Dict, Tuple

from ._models import StockScore


def _detect_super_b1(klines: List[Dict], score: StockScore) -> bool:
    """超级B1战法检测（放量下跌+缩量企稳+J负值）。"""
    from modules.strategies import detect_sb1
    for i in range(max(10, len(klines) - 5), len(klines)):
        sig = detect_sb1(klines, i)
        if sig:
            score.warnings.append(f"超级B1 J={sig.details.get('j', 0):.1f}")
            return True
    return False


def _detect_changan(klines: List[Dict], score: StockScore) -> bool:
    """长安战法检测（B1+放量长阳+缩半量）。"""
    from modules.strategies import detect_changan
    for i in range(max(3, len(klines) - 5), len(klines)):
        sig = detect_changan(klines, i)
        if sig:
            score.reasons.append("长安战法 胜率75%")
            return True
    return False


def _detect_b2_breakout(klines: List[Dict], score: StockScore) -> bool:
    """B2突破战法检测（涨幅≥4%+放量+J<55+无上影线）。"""
    from modules.strategies import detect_b2
    for i in range(max(15, len(klines) - 5), len(klines)):
        sig = detect_b2(klines, i)
        if sig:
            score.reasons.append(f"B2突破 涨{sig.details.get('pct_chg', 0):.1f}%")
            return True
    return False


def _detect_b3_consensus(klines: List[Dict], score: StockScore) -> bool:
    """B3分歧转一致战法检测。"""
    from modules.strategies import detect_b3
    for i in range(max(20, len(klines) - 5), len(klines)):
        sig = detect_b3(klines, i)
        if sig:
            score.reasons.append("B3分歧转一致")
            return True
    return False


def _filter_advanced_strategy(klines: List[Dict], criteria: str, score: StockScore) -> bool:
    """
    高级战法筛选：super_b1 / changan / b2_breakout / b3_consensus。
    detect_* 需要含 is_beidou / is_suoliang 等派生字段的"富"K线。get_recent_klines
    现已统一返回富 dict（见 modules.kline_data），klines 本身即可直接喂给 detect_*，
    无需再向 strategies.core 二次取数（旧 thin→rich 二次取数正是 KeyError 之源）。
    """
    if not klines:
        return False
    if criteria == "super_b1":
        return _detect_super_b1(klines, score)
    if criteria == "changan":
        return _detect_changan(klines, score)
    if criteria == "b2_breakout":
        return _detect_b2_breakout(klines, score)
    if criteria == "b3_consensus":
        return _detect_b3_consensus(klines, score)
    return False


def _filter_p2_strategy(klines: List[Dict], criteria: str, score: StockScore) -> bool:
    """P2 指标选股策略：build_wave / xishou / safe。"""
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
    kirin = detect_kirin_stage(daily_klines)

    if criteria == "build_wave" and wave['wave'] == '建仓波' and wave['confidence'] >= 0.5:
        score.reasons.append(f"建仓波(conf={wave['confidence']})")
        return True
    if criteria == "xishou" and kirin['stage'] == '吸筹' and kirin['confidence'] >= 0.5:
        score.reasons.append(f"吸筹({kirin['sub_type']}, conf={kirin['confidence']})")
        return True
    if criteria == "safe":
        is_safe = (wave['wave'] != '冲刺波' and
                   kirin['stage'] not in ('派发', '回落'))
        if is_safe:
            score.reasons.append(f"安全：{wave['wave']}+{kirin['stage']}")
            return True
    return False


def _filter_stock(result: Tuple[str, List[Dict], StockScore], criteria: str) -> bool:
    """
    判断单只股票是否满足选股条件
    在主进程串行执行（筛选逻辑快，不需要并行）
    """
    _, klines, score = result

    # 基础选股策略
    if criteria == "b1" and score.b1_score >= 50:
        return True
    if criteria == "perfect" and score.score >= 65:
        return True
    if criteria == "oversold" and score.trend_score <= 40:
        return True
    if criteria == "breakout" and score.volume_score >= 70:
        return True

    # 高级选股策略（基于战法检测）
    if criteria in ("super_b1", "changan", "b2_breakout", "b3_consensus"):
        return _filter_advanced_strategy(klines, criteria, score)

    # P2 指标选股策略
    if criteria in ("build_wave", "xishou", "safe"):
        return _filter_p2_strategy(klines, criteria, score)

    return False
