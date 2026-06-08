"""
strategies.orchestrator — 战法编排层

将所有战法检测器串联成完整的「全量扫描→后处理」流水线。
从 __init__ 迁移而来，保持行为完全不变。
"""

from typing import List, Dict, Any, Optional, Tuple

from .core import (
    StrategyType, Priority, Action, StrategySignal,
    get_kline_data,
    _dict_to_daily,
    _calc_kdj, _calc_bbi,
)
from .base_strategies import detect_b1, detect_b2, detect_b3, detect_sb1
from .compound_strategies import (
    detect_changan, detect_sifen_zhiyi_sanyin, detect_nana,
    detect_yidong_dilian, detect_pinghang, detect_kengqi, detect_duichen_va,
)
from .sell_signals import detect_s1, detect_s2, detect_s3, detect_brick_signals, _calc_dif


# ---------------------------------------------------------------------------
# Backward-compatibility helpers (kept here to avoid breaking importers)
# ---------------------------------------------------------------------------

def calculate_ma(prices: List[float], period: int) -> float:
    """已废弃：请使用 indicators.calculate_ma"""
    from ..indicators import calculate_ma as _calc_ma_ind
    return _calc_ma_ind(prices, period)


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """已废弃：请使用 indicators.calculate_kdj（接收 DailyData）"""
    return _calc_kdj(klines)


def calculate_bbi(klines: List[Dict]) -> float:
    """已废弃：请使用 indicators.calculate_bbi（接收 DailyData）"""
    return _calc_bbi(klines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post_process_signals(signals: List[StrategySignal]) -> List[StrategySignal]:
    """
    信号后处理：
    1. 按日期+策略类型去重（同一天同一类型只保留置信度最高的）
    2. 按优先级和日期排序
    3. 截断：最多保留最近30个信号，且每个类型最多保留最近3个
    """
    if not signals:
        return []

    # 1. 去重：同一天同一策略类型，保留置信度最高的
    key_map: Dict[Tuple[str, str], StrategySignal] = {}
    for s in signals:
        key = (s.trade_date, s.strategy.value)
        if key not in key_map or s.confidence > key_map[key].confidence:
            key_map[key] = s

    deduped = list(key_map.values())

    # 2. 按优先级降序、日期降序排序
    deduped.sort(key=lambda x: (x.priority.value, x.confidence, x.trade_date), reverse=True)

    # 3. 截断：每个策略类型最多保留3个最新信号，总体最多30个
    type_counts: Dict[str, int] = {}
    filtered: list[StrategySignal] = []
    for s in deduped:
        type_key = s.strategy.value
        if type_counts.get(type_key, 0) >= 3:
            continue
        if len(filtered) >= 30:
            break
        type_counts[type_key] = type_counts.get(type_key, 0) + 1
        filtered.append(s)

    # 最终按日期降序输出（用户看时间线最自然）
    filtered.sort(key=lambda x: x.trade_date, reverse=True)
    return filtered


def _make_fast_lookups(
    daily_klines: list,
) -> Tuple[Any, Any, Any, Any]:
    """
    预计算 KDJ / BBI 序列，返回两个快速查表闭包以及两个原始函数引用。
    返回: (fast_calc_kdj, fast_calc_bbi, orig_kdj, orig_bbi)
    """
    from ..indicators import precompute_kdj_sequence, precompute_bbi_sequence

    kdj_sequence = precompute_kdj_sequence(daily_klines)
    bbi_sequence = precompute_bbi_sequence(daily_klines)

    def _fast_calc_kdj(klines_slice: List[Dict]) -> Tuple[float, float, float]:
        idx = len(klines_slice) - 1
        return kdj_sequence[idx]

    def _fast_calc_bbi(klines_slice: List[Dict]) -> float:
        idx = len(klines_slice) - 1
        return bbi_sequence[idx]

    from . import core as _core
    orig_kdj = _core._calc_kdj
    orig_bbi = _core._calc_bbi

    return _fast_calc_kdj, _fast_calc_bbi, orig_kdj, orig_bbi


def _patch_fast_calcs(fast_kdj: Any, fast_bbi: Any) -> None:
    """Monkey-patch KDJ/BBI calcs on the submodules to use precomputed sequences."""
    from . import core as _core
    from . import base_strategies as _base
    from . import compound_strategies as _compound

    _core._calc_kdj = fast_kdj
    _core._calc_bbi = fast_bbi
    _base._calc_kdj = fast_kdj
    _base._calc_bbi = fast_bbi
    _compound._calc_kdj = fast_kdj


def _restore_orig_calcs(orig_kdj: Any, orig_bbi: Any) -> None:
    """Restore original KDJ/BBI calcs after fast-path processing."""
    from . import core as _core
    from . import base_strategies as _base
    from . import compound_strategies as _compound

    _core._calc_kdj = orig_kdj
    _core._calc_bbi = orig_bbi
    _base._calc_kdj = orig_kdj
    _base._calc_bbi = orig_bbi
    _compound._calc_kdj = orig_kdj


def _run_per_day_detectors(
    klines: List[Dict],
    daily_klines: list,
    dif_list: List[float],
) -> List[StrategySignal]:
    """
    遍历每一天（从第20根开始），对每个切片运行所有单日战法检测器。
    返回原始（未后处理）信号列表。
    """
    from ..indicators import detect_kirin_stage

    signals: List[StrategySignal] = []
    for i in range(20, len(klines)):
        kirin_context = detect_kirin_stage(daily_klines[:i + 1])

        _append_if(signals, detect_b1(klines, i, kirin_context=kirin_context))
        _append_if(signals, detect_b2(klines, i, kirin_context=kirin_context))
        _append_if(signals, detect_b3(klines, i))
        _append_if(signals, detect_sb1(klines, i))
        _append_if(signals, detect_changan(klines, i, kirin_context=kirin_context))
        _append_if(signals, detect_sifen_zhiyi_sanyin(klines, i))
        _append_if(signals, detect_nana(klines, i, kirin_context=kirin_context))
        _append_if(signals, detect_yidong_dilian(klines, i))
        _append_if(signals, detect_pinghang(klines, i))
        _append_if(signals, detect_kengqi(klines, i))
        _append_if(signals, detect_duichen_va(klines, i))
        _append_if(signals, detect_s1(klines, i, kirin_context=kirin_context))
        _append_if(signals, detect_s2(klines, i, dif_list=dif_list))
        _append_if(signals, detect_s3(klines, i))
        _append_if(signals, detect_brick_signals(klines, i))

    return signals


def _append_if(signals: List[StrategySignal], signal: Optional[StrategySignal]) -> None:
    """Append signal to list only when it is not None."""
    if signal:
        signals.append(signal)


def _run_global_p1_indicators(
    ts_code: str,
    klines: List[Dict],
    daily_klines: list,
) -> List[StrategySignal]:
    """
    全局 P1 指标检测（针对最新一天）：
    滴滴战法、MACD 金叉空/死叉多、出货五式、灾后重建、跃跃欲试、关键K。
    """
    from ..indicators import (
        detect_didi, detect_macd_trap,
        detect_chuhuo_wushi, detect_zaihou_chongjian,
        detect_yueyueyushi, detect_key_candle,
        calculate_macd,
    )

    signals: List[StrategySignal] = []
    last_date = klines[-1]['trade_date']
    last_close = klines[-1]['close']

    # 滴滴战法
    didi_result = detect_didi(daily_klines)
    if didi_result.get('is_didi'):
        signals.append(StrategySignal(
            ts_code=ts_code,
            trade_date=last_date,
            strategy=StrategyType.S1,
            action=Action.SELL.value,
            confidence=0.95,
            description=(
                f"滴滴战法：高位连续两根阴线下台阶，第二根收盘{didi_result['second_close']}"
                f" < 第一根最低{didi_result['first_low']}，量未缩{didi_result['volume_ratio']}倍"
            ),
            price=last_close,
            reason=(
                f"滴滴战法：高位连续两根阴线下台阶，第二根收盘({didi_result['second_close']})"
                f" < 第一根最低({didi_result['first_low']})，量未缩({didi_result['volume_ratio']}倍)"
            ),
        ))

    # MACD 金叉空 / 死叉多
    dif_list_all, dea_list_all, _ = calculate_macd(daily_klines)
    if dif_list_all and dea_list_all:
        trap = detect_macd_trap(dif_list_all, dea_list_all)
        if trap.get('is_gold_trap'):
            signals.append(StrategySignal(
                ts_code=ts_code,
                trade_date=last_date,
                strategy=StrategyType.S1,
                action=Action.SELL.value,
                confidence=0.85,
                description="MACD 金叉空：眼看金叉未成，白线拐头向下，诱多陷阱",
                price=last_close,
                reason="MACD 金叉空：眼看金叉未成，白线拐头向下，诱多陷阱",
            ))
        if trap.get('is_dead_trap'):
            signals.append(StrategySignal(
                ts_code=ts_code,
                trade_date=last_date,
                strategy=StrategyType.B1,
                action=Action.BUY.value,
                confidence=0.85,
                description="MACD 死叉多：眼看死叉未成，白线拐头向上，空中加油",
                price=last_close,
                reason="MACD 死叉多：眼看死叉未成，白线拐头向上，空中加油",
            ))

    # 主力出货五式
    chuhuo = detect_chuhuo_wushi(daily_klines)
    if chuhuo.get('is_selling') and chuhuo.get('patterns'):
        top = chuhuo['patterns'][0]
        signals.append(StrategySignal(
            ts_code=ts_code,
            trade_date=last_date,
            strategy=StrategyType.S1,
            action=Action.SELL.value,
            confidence=top['confidence'],
            description=f"出货五式：{top['type']} - {top['desc']}",
            price=last_close,
            reason=f"出货五式：{top['type']} - {top['desc']}",
        ))

    # 灾后重建
    rebuild = detect_zaihou_chongjian(daily_klines)
    if rebuild.get('is_rebuild'):
        signals.append(StrategySignal(
            ts_code=ts_code,
            trade_date=last_date,
            strategy=StrategyType.B1,
            action=Action.BUY.value,
            confidence=rebuild['confidence'],
            description=rebuild['desc'],
            price=last_close,
            reason=rebuild['desc'],
        ))

    # 跃跃欲试
    ready = detect_yueyueyushi(daily_klines)
    if ready.get('is_ready'):
        signals.append(StrategySignal(
            ts_code=ts_code,
            trade_date=last_date,
            strategy=StrategyType.B2,
            action=Action.BUY.value,
            confidence=ready['confidence'],
            description=ready['desc'],
            price=last_close,
            reason=ready['desc'],
        ))

    # 关键K
    key_k = detect_key_candle(daily_klines)
    if key_k.get('is_key'):
        sig_type = StrategyType.S1 if '阴破位' in key_k.get('type', '') else StrategyType.B1
        signals.append(StrategySignal(
            ts_code=ts_code,
            trade_date=last_date,
            strategy=sig_type,
            action=Action.SELL.value if sig_type == StrategyType.S1 else Action.BUY.value,
            confidence=key_k['confidence'],
            description=f"关键K：{key_k['type']} - {key_k['direction']}",
            price=last_close,
            reason=f"关键K：{key_k['type']} - {key_k['direction']}",
        ))

    return signals


def _run_global_p2_indicators(
    ts_code: str,
    klines: List[Dict],
    daily_klines: list,
) -> List[StrategySignal]:
    """
    全局 P2 指标检测（三波理论 + 麒麟会四阶段）。
    """
    from ..indicators import detect_three_waves, detect_kirin_stage

    signals: List[StrategySignal] = []
    last_date = klines[-1]['trade_date']
    last_close = klines[-1]['close']

    # 三波理论
    wave = detect_three_waves(daily_klines)
    if wave['wave'] != '未知' and wave['confidence'] >= 0.5:
        wave_map = {
            '建仓波': (StrategyType.B1, Action.BUY, f"三波理论·建仓波：{wave['stats']['gain_pct']}% 涨幅，B1可干"),
            '拉升波': (StrategyType.WATCH, Action.HOLD, f"三波理论·拉升波：{wave['stats']['gain_pct']}% 涨幅，等回调"),
            '冲刺波': (StrategyType.S1, Action.SELL, f"三波理论·冲刺波：{wave['stats']['gain_pct']}% 涨幅，不看"),
        }
        if wave['wave'] in wave_map:
            st, act, desc = wave_map[wave['wave']]
            signals.append(StrategySignal(
                ts_code=ts_code,
                trade_date=last_date,
                strategy=st,
                action=act.value,
                confidence=wave['confidence'],
                description=desc,
                details={'price': last_close},
                priority=Priority.OPPORTUNITY if st in (StrategyType.B1, StrategyType.B2) else Priority.OBSERVE,
            ))

    # 麒麟会四阶段
    kirin = detect_kirin_stage(daily_klines)
    if kirin['stage'] != '未知' and kirin['confidence'] >= 0.4:
        kirin_map = {
            '吸筹': (StrategyType.XISHOU, Action.WATCH, f"麒麟会·吸筹：{kirin['sub_type']}，关注等B1"),
            '拉升': (StrategyType.LASHENG, Action.HOLD, f"麒麟会·拉升：{kirin['sub_type']}，不追等回调"),
            '派发': (StrategyType.PAIFA, Action.SELL, f"麒麟会·派发：{kirin['sub_type']}，准备走人"),
            '回落': (StrategyType.LUOLUO, Action.SELL, f"麒麟会·回落：{kirin['sub_type']}，不抄底"),
        }
        if kirin['stage'] in kirin_map:
            st, act, desc = kirin_map[kirin['stage']]
            signals.append(StrategySignal(
                ts_code=ts_code,
                trade_date=last_date,
                strategy=st,
                action=act.value,
                confidence=kirin['confidence'],
                description=desc,
                details={'price': last_close},
                priority=Priority.OBSERVE,
            ))

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all_strategies(ts_code: str, days: int = 120) -> List[StrategySignal]:
    """
    检测所有战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        战法信号列表
    """
    klines = get_kline_data(ts_code, days)
    if not klines:
        return []

    daily_klines = _dict_to_daily(klines)
    fast_kdj, fast_bbi, orig_kdj, orig_bbi = _make_fast_lookups(daily_klines)
    _patch_fast_calcs(fast_kdj, fast_bbi)

    try:
        dif_list = _calc_dif(klines)
        signals = _run_per_day_detectors(klines, daily_klines, dif_list)

        if daily_klines:
            signals.extend(_run_global_p1_indicators(ts_code, klines, daily_klines))
            signals.extend(_run_global_p2_indicators(ts_code, klines, daily_klines))

        signals = _post_process_signals(signals)

    finally:
        _restore_orig_calcs(orig_kdj, orig_bbi)

    return signals


def get_latest_signal(ts_code: str, days: int = 120) -> Optional[StrategySignal]:
    """
    获取最新战法信号

    Args:
        ts_code: 股票代码
        days: 分析天数

    Returns:
        最新战法信号
    """
    signals = detect_all_strategies(ts_code, days)
    return signals[0] if signals else None


def format_signal(signal: StrategySignal) -> str:
    """格式化输出信号"""
    action_emoji = {
        'BUY': '[买入]',
        'SELL': '[卖出]',
        'HOLD': '[持有]',
        'WATCH': '[观望]',
    }

    return f"""
{'='*60}
{signal.strategy.value} 信号
{'='*60}
股票: {signal.ts_code}
日期: {signal.trade_date}
置信度: {signal.confidence*100:.0f}%
描述: {signal.description}

交易建议: {action_emoji.get(signal.action, signal.action)}
{f'目标价: {signal.target_price:.2f}' if signal.target_price else ''}
{f'止损价: {signal.stop_loss:.2f}' if signal.stop_loss else ''}

详细: {signal.details}
{'='*60}
"""


def analyze_with_strategies(ts_code: str, days: int = 120) -> Dict[str, Any]:
    """
    综合战法分析

    Returns:
        分析结果字典
    """
    signals = detect_all_strategies(ts_code, days)

    # 按战法类型分组统计
    strategy_stats: Dict[str, Dict[str, Any]] = {}
    for s in signals:
        name = s.strategy.value
        if name not in strategy_stats:
            strategy_stats[name] = {
                'count': 0,
                'signals': []
            }
        strategy_stats[name]['count'] += 1
        strategy_stats[name]['signals'].append(s)

    # 最新信号
    latest = signals[0] if signals else None

    return {
        'ts_code': ts_code,
        'total_signals': len(signals),
        'strategy_stats': strategy_stats,
        'latest_signal': latest,
        'all_signals': signals[:20],  # 最近20个信号
    }
