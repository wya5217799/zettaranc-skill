"""
选股主逻辑：screen_stocks（支持多进程并行）
"""

import os
from typing import List

from ._models import StockScore
from ._data import get_all_stocks
from ._scoring import _analyze_worker
from ._filters import _filter_stock

# 并行化阈值：小于此数量不启用多进程（启动开销不值得）
_PARALLEL_THRESHOLD = 50


def screen_stocks(criteria: str = "b1", max_stocks: int = 0,
                  max_workers: int = 0, use_parallel: bool = True) -> List[StockScore]:
    """
    选股筛选（支持多进程并行）

    criteria:
    - "b1": B1买点机会
    - "perfect": 完美图形
    - "breakout": 突破形态
    - "oversold": 超跌反弹
    - "super_b1": 超级B1（放量下跌+缩量企稳+J负值）
    - "changan": 长安战法（B1+放量长阳+缩半量）
    - "b2_breakout": B2突破（涨幅≥4%+放量+J<55+无上影线）
    - "b3_consensus": B3分歧转一致
    - "build_wave": 建仓波（三波理论·建仓波）
    - "xishou": 吸筹阶段（麒麟会·吸筹）
    - "safe": 安全选股（非冲刺波 + 非派发/回落）

    max_stocks: 最大扫描数量，0=全量（默认500只性能保护）
    max_workers: 并行进程数，0=自动（CPU核心数）
    use_parallel: 是否启用多进程并行（<50只时自动关闭）

    返回：满足条件的 StockScore 列表（按评分降序）
    """
    stocks = get_all_stocks()
    limit = max_stocks if max_stocks > 0 else 500
    stocks = stocks[:limit]

    results: List[StockScore] = []

    # 小数据量时禁用并行（启动开销不值得）
    if not use_parallel or len(stocks) < _PARALLEL_THRESHOLD:
        # 串行模式
        for stock in stocks:
            result = _analyze_worker(stock['ts_code'])
            if result and _filter_stock(result, criteria):
                results.append(result[2])
    else:
        # 并行模式：只并行 analyze_stock，筛选在主进程串行
        workers = max_workers or os.cpu_count() or 4
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            ts_codes = [s['ts_code'] for s in stocks]

            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(_analyze_worker, ts_code): ts_code
                    for ts_code in ts_codes
                }
                for future in as_completed(future_map):
                    result = future.result()
                    if result and _filter_stock(result, criteria):
                        results.append(result[2])
        except Exception:
            # 并行失败回退到串行
            for stock in stocks:
                result = _analyze_worker(stock['ts_code'])
                if result and _filter_stock(result, criteria):
                    results.append(result[2])

    # 按评分排序
    results.sort(key=lambda x: x.score, reverse=True)
    return results
