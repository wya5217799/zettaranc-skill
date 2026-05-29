#!/usr/bin/env python3
"""
Tushare Pro 高权限数据抓取脚本
15000 积分接口调用，数据保存到 SQLite 数据库

使用方式:
    python scripts/fetch_tushare_data.py --help
    python scripts/fetch_tushare_data.py stock_basic
    python scripts/fetch_tushare_data.py daily 000001.SZ --start 20260101 --end 20260501
    python scripts/fetch_tushare_data.py moneyflow 000001.SZ --date 20260509
    python scripts/fetch_tushare_data.py limit_list --date 20260509
    python scripts/fetch_tushare_data.py top_list --date 20260509
    python scripts/fetch_tushare_data.py fina_indicator 000001.SZ --start 20250101 --end 20250501
    python scripts/fetch_tushare_data.py dividend 000001.SZ
    python scripts/fetch_tushare_data.py top10_holders 000001.SZ --date 20250501
    python scripts/fetch_tushare_data.py daily_hsgt --start 20260101 --end 20260501
    python scripts/fetch_tushare_data.py stock_top10_hsgt --date 20260509
    python scripts/fetch_tushare_data.py concept_detail --code ie018
    python scripts/fetch_tushare_data.py index_daily 000001.SH --start 20260101 --end 20260501
    python scripts/fetch_tushare_data.py index_weight 000001.SH --date 20250501
    python scripts/fetch_tushare_data.py realtime_quote --codes 600000.SH,000001.SZ
    python scripts/fetch_tushare_data.py all
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tushare as ts
    from dotenv import load_dotenv
except ImportError as e:
    print(f"请先安装依赖: pip install tushare python-dotenv")
    sys.exit(1)

# 加载环境变量
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# 导入数据库模块
from modules.database import get_connection, init_database

# ==================== 配置 ====================
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "")
VERIFY_TOKEN_URL = os.environ.get("TUSHARE_VERIFY_TOKEN_URL", "")

# 限流控制：120次/分钟
MIN_INTERVAL = 60 / 120

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/fetch_tushare.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ==================== 数据库保存函数 ====================

def save_to_db(data_type: str, df, ts_code: str = None) -> int:
    """
    根据数据类型保存到数据库

    Args:
        data_type: 数据类型标识
        df: Tushare 返回的 DataFrame
        ts_code: 股票代码（用于日志）

    Returns:
        保存的记录数
    """
    if df is None or len(df) == 0:
        return 0

    saved_count = 0
    with get_connection() as conn:
        cursor = conn.cursor()

        if data_type == 'stock_basic':
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_basic
                    (ts_code, name, area, industry, market, list_date, is_hs)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('name'), row.get('area'),
                    row.get('industry'), row.get('market'),
                    row.get('list_date'), row.get('is_hs')
                ))
                saved_count += 1

        elif data_type == 'daily':
            for _, row in df.iterrows():
                # 计算涨跌停标记
                pct_chg = row.get('pct_chg', 0) or 0
                is_limit_up = 1 if pct_chg >= 9.9 else 0
                is_limit_down = 1 if pct_chg <= -9.9 else 0

                cursor.execute("""
                    INSERT OR REPLACE INTO daily_kline
                    (ts_code, trade_date, open, high, low, close, vol, amount,
                     pct_chg, vol_ratio, is_limit_up, is_limit_down)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    row.get('open'), row.get('high'), row.get('low'), row.get('close'),
                    row.get('vol'), row.get('amount'), row.get('pct_chg'),
                    row.get('vol_ratio', 1.0), is_limit_up, is_limit_down
                ))
                saved_count += 1

        elif data_type == 'moneyflow':
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO moneyflow
                    (ts_code, trade_date, buy_sm_amount, buy_md_amount,
                     buy_lg_amount, buy_elg_amount, sell_sm_amount, sell_md_amount,
                     sell_lg_amount, sell_elg_amount, net_mf, pct_mf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    row.get('buy_sm_amount'), row.get('buy_md_amount'),
                    row.get('buy_lg_amount'), row.get('buy_elg_amount'),
                    row.get('sell_sm_amount'), row.get('sell_md_amount'),
                    row.get('sell_lg_amount'), row.get('sell_elg_amount'),
                    row.get('net_mf'), row.get('pct_mf')
                ))
                saved_count += 1

        elif data_type == 'financial_data':
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO financial_data
                    (ts_code, ann_date, end_date, report_type, revenue, net_profit,
                     total_assets, total_liab, equity, pe, pb, ps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('ann_date'), row.get('end_date'),
                    row.get('report_type', 1), row.get('revenue'), row.get('net_profit'),
                    row.get('total_assets'), row.get('total_liab'),
                    row.get('equity'), row.get('pe'), row.get('pb'), row.get('ps')
                ))
                saved_count += 1

        elif data_type == 'dividend':
            # 分红送股保存到 financial_data 表（临时）
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO financial_data
                    (ts_code, ann_date, end_date, report_type, revenue, net_profit)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('ann_date'),
                    row.get('end_date'), 99,  # 99表示分红数据
                    row.get('div_ratio'), row.get('share_ratio')
                ))
                saved_count += 1

        elif data_type == 'fina_indicator':
            # 财务指标保存到 financial_data 表
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO financial_data
                    (ts_code, ann_date, end_date, report_type, revenue, net_profit,
                     total_assets, total_liab, equity, pe, pb, ps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('ann_date'), row.get('end_date'),
                    98,  # 98表示财务指标
                    row.get('revenue'), row.get('net_profit'),
                    row.get('total_assets'), row.get('total_liab'),
                    row.get('equity'), row.get('pe'), row.get('pb'), row.get('ps')
                ))
                saved_count += 1

        elif data_type == 'limit_list':
            # 涨跌停列表保存到 trade_signals 表
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO trade_signals
                    (ts_code, signal_date, signal_type, signal_score, signal_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    'LIMIT_UP' if row.get('up_limit', 0) > 0 else 'LIMIT_DOWN',
                    row.get('pct_chg', 0), row.get('close')
                ))
                saved_count += 1

        elif data_type == 'top_list':
            # 龙虎榜保存到 trade_signals 表
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO trade_signals
                    (ts_code, signal_date, signal_type, signal_score, signal_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    'TOP_LIST', row.get('pct_chg', 0), row.get('close')
                ))
                saved_count += 1

        elif data_type == 'concept_detail':
            # 概念股保存到 stock_basic 表的 tags 字段
            for _, row in df.iterrows():
                cursor.execute("""
                    UPDATE stock_basic SET tags = ? WHERE ts_code = ?
                """, (row.get('concept_name', ''), row.get('ts_code')))
                saved_count += 1

        elif data_type == 'index_daily':
            # 指数日线保存到 daily_kline 表（用指数代码作为 ts_code）
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_kline
                    (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    row.get('open'), row.get('high'), row.get('low'), row.get('close'),
                    row.get('vol'), row.get('amount'), row.get('pct_chg')
                ))
                saved_count += 1

        elif data_type == 'daily_hsgt':
            # 沪深港通每日成交保存到 moneyflow 表
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO moneyflow
                    (ts_code, trade_date, buy_sm_amount, buy_md_amount,
                     buy_lg_amount, buy_elg_amount, net_mf, pct_mf)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('trade_date'),
                    row.get('buy_sm_amount', 0), row.get('buy_md_amount', 0),
                    row.get('buy_lg_amount', 0), row.get('buy_elg_amount', 0),
                    row.get('net_mf', 0), row.get('pct_mf', 0)
                ))
                saved_count += 1

        elif data_type == 'top10_holders':
            # 前十大股东保存到 trade_signals 表
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT OR REPLACE INTO trade_signals
                    (ts_code, signal_date, signal_type, signal_score)
                    VALUES (?, ?, ?, ?)
                """, (
                    row.get('ts_code'), row.get('ann_date'),
                    'TOP10_HOLDERS', row.get('hold_ratio', 0)
                ))
                saved_count += 1

        # 记录同步日志
        cursor.execute("""
            INSERT INTO sync_log (data_type, ts_code, last_date, status, message)
            VALUES (?, ?, ?, ?, ?)
        """, (data_type, ts_code or 'ALL',
              datetime.now().strftime('%Y%m%d'), 'success',
              f'Saved {saved_count} records'))

    logger.info(f"[{data_type}] 保存到数据库: {saved_count} 条")
    return saved_count


# ==================== Tushare 抓取器 ====================

class TushareFetcher:
    """Tushare 高权限数据抓取器"""

    def __init__(self):
        if not TUSHARE_TOKEN:
            raise ValueError("未设置 TUSHARE_TOKEN，请检查 .env 文件")

        # 初始化数据库
        init_database()

        # 初始化 Tushare
        ts.set_token(TUSHARE_TOKEN)
        self.pro = ts.pro_api()
        self.pro._DataApi__http_url = TUSHARE_API_URL if TUSHARE_API_URL else None

        # 实时行情需要额外设置
        from tushare.stock import cons as ct
        if VERIFY_TOKEN_URL:
            ct.verify_token_url = VERIFY_TOKEN_URL

        # 限流控制
        self.last_request_time = {}

        logger.info(f"Tushare 抓取器初始化完成，API_URL: {TUSHARE_API_URL or '官方'}")

    def _rate_limit(self, api_name: str):
        """限流控制"""
        now = time.time()
        last = self.last_request_time.get(api_name, 0)
        elapsed = now - last
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self.last_request_time[api_name] = now

    def get_stock_basic(self, ts_code: Optional[str] = None,
                        name: Optional[str] = None,
                        list_status: str = 'L') -> Optional:
        """获取股票基本信息"""
        self._rate_limit("stock_basic")
        try:
            df = self.pro.stock_basic(
                ts_code=ts_code,
                name=name,
                list_status=list_status,
                fields='ts_code,symbol,name,area,industry,market,list_date,delist_date,is_hs'
            )
            logger.info(f"[stock_basic] 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[stock_basic] 获取失败: {e}")
            return None

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取日线行情"""
        self._rate_limit("daily")
        try:
            df = ts.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                adj='qfq',
                api=self.pro,
            )
            logger.info(f"[daily] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[daily] {ts_code} 获取失败: {e}")
            return None

    def get_weekly(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取周线行情"""
        self._rate_limit("weekly")
        try:
            df = self.pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[weekly] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[weekly] {ts_code} 获取失败: {e}")
            return None

    def get_monthly(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取月线行情"""
        self._rate_limit("monthly")
        try:
            df = self.pro.monthly(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[monthly] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[monthly] {ts_code} 获取失败: {e}")
            return None

    def get_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取复权因子"""
        self._rate_limit("adj_factor")
        try:
            df = self.pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[adj_factor] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[adj_factor] {ts_code} 获取失败: {e}")
            return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> Optional:
        """获取个股资金流向"""
        self._rate_limit("moneyflow")
        try:
            df = self.pro.moneyflow(ts_code=ts_code, trade_date=trade_date)
            logger.info(f"[moneyflow] {ts_code} {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[moneyflow] {ts_code} {trade_date} 获取失败: {e}")
            return None

    def get_moneyflow_hsgt(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取沪深港通资金流向"""
        self._rate_limit("moneyflow_hsgt")
        try:
            df = self.pro.moneyflow_hsgt(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[moneyflow_hsgt] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[moneyflow_hsgt] {ts_code} 获取失败: {e}")
            return None

    def get_limit_list(self, trade_date: str, limit_type: str = 'D') -> Optional:
        """获取涨跌停列表"""
        self._rate_limit("limit_list")
        try:
            df = self.pro.limit_list_d(trade_date=trade_date, limit_type=limit_type)
            logger.info(f"[limit_list] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[limit_list] {trade_date} 获取失败: {e}")
            return None

    def get_top_list(self, trade_date: str) -> Optional:
        """获取龙虎榜列表"""
        self._rate_limit("top_list")
        try:
            df = self.pro.top_list(trade_date=trade_date)
            logger.info(f"[top_list] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[top_list] {trade_date} 获取失败: {e}")
            return None

    def get_top_list_hsgt(self, trade_date: str) -> Optional:
        """获取龙虎榜详情（个股）"""
        self._rate_limit("top_list_hsgt")
        try:
            df = self.pro.top_list_hsgt(trade_date=trade_date)
            logger.info(f"[top_list_hsgt] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[top_list_hsgt] {trade_date} 获取失败: {e}")
            return None

    def get_fina_indicator(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取财务指标"""
        self._rate_limit("fina_indicator")
        try:
            df = self.pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[fina_indicator] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[fina_indicator] {ts_code} 获取失败: {e}")
            return None

    def get_financial_report(self, ts_code: str, start_date: str, end_date: str,
                             report_type: str = '1') -> Optional:
        """获取财务报表"""
        self._rate_limit("financial_report")
        try:
            df = self.pro.financial_report(ts_code=ts_code, start_date=start_date,
                                           end_date=end_date, report_type=report_type)
            logger.info(f"[financial_report] {ts_code} type={report_type} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[financial_report] {ts_code} 获取失败: {e}")
            return None

    def get_express(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取业绩快报"""
        self._rate_limit("express")
        try:
            df = self.pro.express(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[express] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[express] {ts_code} 获取失败: {e}")
            return None

    def get_dividend(self, ts_code: str) -> Optional:
        """获取分红送股数据"""
        self._rate_limit("dividend")
        try:
            df = self.pro.dividend(ts_code=ts_code)
            logger.info(f"[dividend] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[dividend] {ts_code} 获取失败: {e}")
            return None

    def get_shareholder(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取股东人数"""
        self._rate_limit("shareholder")
        try:
            df = self.pro.shareholder(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[shareholder] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[shareholder] {ts_code} 获取失败: {e}")
            return None

    def get_top10_holders(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取前十大股东"""
        self._rate_limit("top10_holders")
        try:
            df = self.pro.top10_holders(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[top10_holders] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[top10_holders] {ts_code} 获取失败: {e}")
            return None

    def get_concept_detail(self, code: str) -> Optional:
        """获取概念股详情"""
        self._rate_limit("concept_detail")
        try:
            df = self.pro.concept_detail(code=code)
            logger.info(f"[concept_detail] {code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[concept_detail] {code} 获取失败: {e}")
            return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> Optional:
        """获取指数日线行情"""
        self._rate_limit("index_daily")
        try:
            df = self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            logger.info(f"[index_daily] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[index_daily] {ts_code} 获取失败: {e}")
            return None

    def get_index_weight(self, index_code: str, trade_date: str) -> Optional:
        """获取指数成分和权重"""
        self._rate_limit("index_weight")
        try:
            df = self.pro.index_weight(index_code=index_code, trade_date=trade_date)
            logger.info(f"[index_weight] {index_code} {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[index_weight] {index_code} 获取失败: {e}")
            return None

    def get_daily_hsgt(self, start_date: str, end_date: str) -> Optional:
        """获取沪深港通每日成交情况"""
        self._rate_limit("daily_hsgt")
        try:
            df = self.pro.daily_hsgt(start_date=start_date, end_date=end_date)
            logger.info(f"[daily_hsgt] 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[daily_hsgt] 获取失败: {e}")
            return None

    def get_stock_top10_hsgt(self, trade_date: str) -> Optional:
        """获取个股沪深港通持仓明细"""
        self._rate_limit("stock_top10_hsgt")
        try:
            df = self.pro.stock_top10_hsgt(trade_date=trade_date)
            logger.info(f"[stock_top10_hsgt] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[stock_top10_hsgt] {trade_date} 获取失败: {e}")
            return None

    def get_realtime_quote(self, ts_codes: List[str]) -> Optional:
        """获取A股实时行情（特殊接口）"""
        self._rate_limit("realtime_quote")
        try:
            ts_code_str = ','.join(ts_codes)
            df = ts.realtime_quote(ts_code=ts_code_str)
            logger.info(f"[realtime_quote] {ts_code_str} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[realtime_quote] {ts_code_str} 获取失败: {e}")
            return None

    def get_realtime_tick(self, ts_code: str) -> Optional:
        """获取实时分笔成交数据（特殊接口）"""
        self._rate_limit("realtime_tick")
        try:
            df = ts.realtime_tick(ts_code=ts_code, api=self.pro)
            logger.info(f"[realtime_tick] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[realtime_tick] {ts_code} 获取失败: {e}")
            return None

    def get_pro_bar(self, ts_code: str, start_date: str, end_date: str,
                    adj: str = 'qfq') -> Optional:
        """获取行情数据（pro_bar 方式，特殊接口）"""
        self._rate_limit("pro_bar")
        try:
            df = ts.pro_bar(ts_code=ts_code, api=self.pro,
                           start_date=start_date, end_date=end_date, adj=adj)
            logger.info(f"[pro_bar] {ts_code} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[pro_bar] {ts_code} 获取失败: {e}")
            return None

    def get_fund_nav(self, ts_code: Optional[str] = None, end_date: Optional[str] = None) -> Optional:
        """获取场外基金净值"""
        self._rate_limit("fund_nav")
        try:
            df = self.pro.fund_nav(ts_code=ts_code, end_date=end_date)
            logger.info(f"[fund_nav] {ts_code or '全部'} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[fund_nav] {ts_code} 获取失败: {e}")
            return None

    def get_fut_daily(self, trade_date: str, exchange: str = '') -> Optional:
        """获取期货每日行情"""
        self._rate_limit("fut_daily")
        try:
            df = self.pro.fut_daily(trade_date=trade_date, exchange=exchange)
            logger.info(f"[fut_daily] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[fut_daily] {trade_date} 获取失败: {e}")
            return None

    def get_fut_holding(self, trade_date: str, exchange: str = '', fut_code: str = '') -> Optional:
        """获取期货持仓数据"""
        self._rate_limit("fut_holding")
        try:
            df = self.pro.fut_holding(trade_date=trade_date, exchange=exchange, fut_code=fut_code)
            logger.info(f"[fut_holding] {trade_date} 获取成功，共 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"[fut_holding] {trade_date} 获取失败: {e}")
            return None


# ==================== 命令行接口 ====================

def cmd_stock_basic(args, fetcher):
    """股票基本信息"""
    df = fetcher.get_stock_basic(ts_code=args.ts_code, name=args.name, list_status=args.list_status)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('stock_basic', df)
            print("已保存到数据库")

def cmd_daily(args, fetcher):
    """日线行情"""
    df = fetcher.get_daily(args.ts_code, args.start, args.end)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('daily', df, args.ts_code)
            print("已保存到数据库")

def cmd_moneyflow(args, fetcher):
    """资金流向"""
    df = fetcher.get_moneyflow(args.ts_code, args.date)
    if df is not None:
        print(df)
        if args.save_db:
            save_to_db('moneyflow', df, args.ts_code)
            print("已保存到数据库")

def cmd_limit_list(args, fetcher):
    """涨跌停列表"""
    df = fetcher.get_limit_list(args.date, args.limit_type)
    if df is not None:
        print(df.head(30))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('limit_list', df)
            print("已保存到数据库")

def cmd_top_list(args, fetcher):
    """龙虎榜"""
    df = fetcher.get_top_list(args.date)
    if df is not None:
        print(df.head(30))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('top_list', df)
            print("已保存到数据库")

def cmd_fina_indicator(args, fetcher):
    """财务指标"""
    df = fetcher.get_fina_indicator(args.ts_code, args.start, args.end)
    if df is not None:
        print(df.head(10))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('fina_indicator', df, args.ts_code)
            print("已保存到数据库")

def cmd_financial_report(args, fetcher):
    """财务报表"""
    df = fetcher.get_financial_report(args.ts_code, args.start, args.end, args.report_type)
    if df is not None:
        print(df.head(10))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('financial_report', df, args.ts_code)
            print("已保存到数据库")

def cmd_dividend(args, fetcher):
    """分红送股"""
    df = fetcher.get_dividend(args.ts_code)
    if df is not None:
        print(df)
        if args.save_db:
            save_to_db('dividend', df, args.ts_code)
            print("已保存到数据库")

def cmd_top10_holders(args, fetcher):
    """前十大股东"""
    df = fetcher.get_top10_holders(args.ts_code, args.start, args.end)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('top10_holders', df, args.ts_code)
            print("已保存到数据库")

def cmd_shareholder(args, fetcher):
    """股东人数"""
    df = fetcher.get_shareholder(args.ts_code, args.start, args.end)
    if df is not None:
        print(df)
        if args.save_db:
            save_to_db('shareholder', df, args.ts_code)
            print("已保存到数据库")

def cmd_concept_detail(args, fetcher):
    """概念股详情"""
    df = fetcher.get_concept_detail(args.code)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('concept_detail', df)
            print("已保存到数据库")

def cmd_index_daily(args, fetcher):
    """指数日线"""
    df = fetcher.get_index_daily(args.ts_code, args.start, args.end)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('index_daily', df, args.ts_code)
            print("已保存到数据库")

def cmd_index_weight(args, fetcher):
    """指数权重"""
    df = fetcher.get_index_weight(args.ts_code, args.date)
    if df is not None:
        print(df.head(30))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            # 指数权重保存到 trade_signals
            save_to_db('index_weight', df, args.ts_code)
            print("已保存到数据库")

def cmd_daily_hsgt(args, fetcher):
    """沪深港通每日成交"""
    df = fetcher.get_daily_hsgt(args.start, args.end)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('daily_hsgt', df)
            print("已保存到数据库")

def cmd_stock_top10_hsgt(args, fetcher):
    """个股沪深港通持仓明细"""
    df = fetcher.get_stock_top10_hsgt(args.date)
    if df is not None:
        print(df.head(30))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('stock_top10_hsgt', df)
            print("已保存到数据库")

def cmd_realtime_quote(args, fetcher):
    """实时行情"""
    df = fetcher.get_realtime_quote(args.ts_codes)
    if df is not None:
        print(df)
        if args.save_db:
            # 实时行情只打印，不保存（时效性太强）
            print("(实时行情不保存到数据库)")

def cmd_realtime_tick(args, fetcher):
    """实时分笔成交"""
    df = fetcher.get_realtime_tick(args.ts_code)
    if df is not None:
        print(df)
        if args.save_db:
            print("(实时分笔不保存到数据库)")

def cmd_pro_bar(args, fetcher):
    """pro_bar 行情"""
    df = fetcher.get_pro_bar(args.ts_code, args.start, args.end, args.adj)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            save_to_db('daily', df, args.ts_code)
            print("已保存到数据库")

def cmd_fund_nav(args, fetcher):
    """场外基金净值"""
    df = fetcher.get_fund_nav(ts_code=args.ts_code, end_date=args.date)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            print("(基金净值暂不保存到数据库)")

def cmd_fut_daily(args, fetcher):
    """期货每日行情"""
    df = fetcher.get_fut_daily(args.trade_date, args.exchange)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            print("(期货数据暂不保存到数据库)")

def cmd_fut_holding(args, fetcher):
    """期货持仓"""
    df = fetcher.get_fut_holding(args.trade_date, args.exchange, args.fut_code)
    if df is not None:
        print(df.head(20))
        print(f"\n共 {len(df)} 条记录")
        if args.save_db:
            print("(期货数据暂不保存到数据库)")


def cmd_all(args, fetcher):
    """抓取所有主要数据（测试用）"""
    today = datetime.now().strftime('%Y%m%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    print("=" * 50)
    print("开始抓取所有主要数据...")
    print("=" * 50)

    total_saved = 0

    # 股票基本信息
    print("\n[1/10] 股票基本信息...")
    df = fetcher.get_stock_basic()
    if df is not None:
        print(f"  获取到 {len(df)} 只股票")
        if args.save_db:
            total_saved += save_to_db('stock_basic', df)

    # 指数日线（上证指数）
    print("\n[2/10] 上证指数日线...")
    df = fetcher.get_index_daily('000001.SH', '20260101', today)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('index_daily', df, '000001.SH')

    # 沪深港通每日成交
    print("\n[3/10] 沪深港通每日成交...")
    df = fetcher.get_daily_hsgt('20260101', today)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('daily_hsgt', df)

    # 资金流向示例
    print("\n[4/10] 个股资金流向 (平安银行)...")
    df = fetcher.get_moneyflow('000001.SZ', yesterday)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('moneyflow', df, '000001.SZ')

    # 财务指标示例
    print("\n[5/10] 财务指标 (平安银行)...")
    df = fetcher.get_fina_indicator('000001.SZ', '20250101', today)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('fina_indicator', df, '000001.SZ')

    # 分红送股示例
    print("\n[6/10] 分红送股 (平安银行)...")
    df = fetcher.get_dividend('000001.SZ')
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('dividend', df, '000001.SZ')

    # 概念股示例
    print("\n[7/10] 概念股详情 (人工智能)...")
    df = fetcher.get_concept_detail('TS2')  # 人工智能
    if df is not None:
        print(f"  获取到 {len(df)} 只概念股")
        if args.save_db:
            total_saved += save_to_db('concept_detail', df)

    # 实时行情示例
    print("\n[8/10] 实时行情 (平安银行)...")
    df = fetcher.get_realtime_quote(['000001.SZ'])
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        print("(实时行情不保存到数据库)")

    # 基金净值示例
    print("\n[9/10] 基金净值...")
    df = fetcher.get_fund_nav(end_date=today)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        print("(基金净值暂不保存到数据库)")

    # pro_bar 示例
    print("\n[10/10] pro_bar 行情 (比亚迪)...")
    df = fetcher.get_pro_bar('002594.SZ', '20260101', today)
    if df is not None:
        print(f"  获取到 {len(df)} 条")
        if args.save_db:
            total_saved += save_to_db('daily', df, '002594.SZ')

    print("\n" + "=" * 50)
    if args.save_db:
        print(f"抓取完成! 共保存 {total_saved} 条记录到数据库")
    else:
        print("抓取完成!")
    print("=" * 50)


# ==================== 主程序 ====================

def main():
    parser = argparse.ArgumentParser(description='Tushare Pro 高权限数据抓取工具',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""
示例:
  python scripts/fetch_tushare_data.py stock_basic
  python scripts/fetch_tushare_data.py daily 000001.SZ --start 20260101 --end 20260501 --save-db
  python scripts/fetch_tushare_data.py moneyflow 000001.SZ --date 20260509 --save-db
  python scripts/fetch_tushare_data.py limit_list --date 20260509 --save-db
  python scripts/fetch_tushare_data.py top_list --date 20260509 --save-db
  python scripts/fetch_tushare_data.py realtime_quote --codes 600000.SH,000001.SZ
  python scripts/fetch_tushare_data.py all --save-db
                                    """)

    parser.add_argument('--save-db', action='store_true', help='保存结果到数据库（默认开启）')
    parser.add_argument('--no-save', action='store_true', help='不保存，仅查看数据')
    parser.add_argument('--debug', action='store_true', help='开启调试模式')

    subparsers = parser.add_subparsers(dest='command', help='数据抓取命令')

    # stock_basic
    p = subparsers.add_parser('stock_basic', help='股票基本信息')
    p.add_argument('--ts_code', help='股票代码')
    p.add_argument('--name', help='股票名称')
    p.add_argument('--list_status', default='L', choices=['L', 'D', 'P'], help='上市状态 L-上市 D-退市 P-暂停')

    # daily
    p = subparsers.add_parser('daily', help='日线行情')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20260101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # moneyflow
    p = subparsers.add_parser('moneyflow', help='资金流向')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')

    # limit_list
    p = subparsers.add_parser('limit_list', help='涨跌停列表')
    p.add_argument('--date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')
    p.add_argument('--limit_type', default='D', choices=['D', 'U'], help='涨停/跌停 D-涨停 U-跌停')

    # top_list
    p = subparsers.add_parser('top_list', help='龙虎榜')
    p.add_argument('--date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')

    # fina_indicator
    p = subparsers.add_parser('fina_indicator', help='财务指标')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20250101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # financial_report
    p = subparsers.add_parser('financial_report', help='财务报表')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20250101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')
    p.add_argument('--report_type', default='1', choices=['1', '2', '3', '4'],
                   help='报表类型 1-利润表 2-资产负债表 3-现金流量表 4-所有者权益变动表')

    # dividend
    p = subparsers.add_parser('dividend', help='分红送股')
    p.add_argument('ts_code', help='股票代码')

    # top10_holders
    p = subparsers.add_parser('top10_holders', help='前十大股东')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20250101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # shareholder
    p = subparsers.add_parser('shareholder', help='股东人数')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20250101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # concept_detail
    p = subparsers.add_parser('concept_detail', help='概念股详情')
    p.add_argument('code', help='概念代码')

    # index_daily
    p = subparsers.add_parser('index_daily', help='指数日线')
    p.add_argument('ts_code', help='指数代码')
    p.add_argument('--start', default='20260101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # index_weight
    p = subparsers.add_parser('index_weight', help='指数权重')
    p.add_argument('ts_code', help='指数代码')
    p.add_argument('--date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')

    # daily_hsgt
    p = subparsers.add_parser('daily_hsgt', help='沪深港通每日成交')
    p.add_argument('--start', default='20260101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')

    # stock_top10_hsgt
    p = subparsers.add_parser('stock_top10_hsgt', help='个股沪深港通持仓明细')
    p.add_argument('--date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')

    # realtime_quote
    p = subparsers.add_parser('realtime_quote', help='实时行情（特殊接口）')
    p.add_argument('--codes', default='600000.SH,000001.SZ', help='股票代码，逗号分隔')

    # realtime_tick
    p = subparsers.add_parser('realtime_tick', help='实时分笔（特殊接口）')
    p.add_argument('ts_code', help='股票代码')

    # pro_bar
    p = subparsers.add_parser('pro_bar', help='pro_bar 行情（特殊接口）')
    p.add_argument('ts_code', help='股票代码')
    p.add_argument('--start', default='20260101', help='开始日期 YYYYMMDD')
    p.add_argument('--end', help='结束日期 YYYYMMDD')
    p.add_argument('--adj', default='qfq', choices=['qfq', 'hfq', 'None'], help='复权方式')

    # fund_nav
    p = subparsers.add_parser('fund_nav', help='场外基金净值')
    p.add_argument('--ts_code', help='基金代码')
    p.add_argument('--date', help='结束日期 YYYYMMDD')

    # fut_daily
    p = subparsers.add_parser('fut_daily', help='期货每日行情')
    p.add_argument('--trade_date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')
    p.add_argument('--exchange', default='', help='交易所 CZCE-郑商所 DCE-大商所 SHFE-上期所 INE-能源中心')

    # fut_holding
    p = subparsers.add_parser('fut_holding', help='期货持仓')
    p.add_argument('--trade_date', default=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), help='交易日期 YYYYMMDD')
    p.add_argument('--exchange', default='', help='交易所')
    p.add_argument('--fut_code', default='', help='期货合约代码')

    # all
    subparsers.add_parser('all', help='抓取所有主要数据（测试用）')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # 默认保存到数据库，除非指定 --no-save
    if not hasattr(args, 'save_db'):
        args.save_db = True

    if args.no_save:
        args.save_db = False

    if not args.command:
        parser.print_help()
        return

    try:
        fetcher = TushareFetcher()

        # 命令分发
        commands = {
            'stock_basic': (cmd_stock_basic, ['ts_code', 'name', 'list_status']),
            'daily': (cmd_daily, ['ts_code', 'start', 'end']),
            'moneyflow': (cmd_moneyflow, ['ts_code', 'date']),
            'limit_list': (cmd_limit_list, ['date', 'limit_type']),
            'top_list': (cmd_top_list, ['date']),
            'fina_indicator': (cmd_fina_indicator, ['ts_code', 'start', 'end']),
            'financial_report': (cmd_financial_report, ['ts_code', 'start', 'end', 'report_type']),
            'dividend': (cmd_dividend, ['ts_code']),
            'top10_holders': (cmd_top10_holders, ['ts_code', 'start', 'end']),
            'shareholder': (cmd_shareholder, ['ts_code', 'start', 'end']),
            'concept_detail': (cmd_concept_detail, ['code']),
            'index_daily': (cmd_index_daily, ['ts_code', 'start', 'end']),
            'index_weight': (cmd_index_weight, ['ts_code', 'date']),
            'daily_hsgt': (cmd_daily_hsgt, ['start', 'end']),
            'stock_top10_hsgt': (cmd_stock_top10_hsgt, ['date']),
            'realtime_quote': (cmd_realtime_quote, ['ts_codes']),
            'realtime_tick': (cmd_realtime_tick, ['ts_code']),
            'pro_bar': (cmd_pro_bar, ['ts_code', 'start', 'end', 'adj']),
            'fund_nav': (cmd_fund_nav, ['ts_code', 'date']),
            'fut_daily': (cmd_fut_daily, ['trade_date', 'exchange']),
            'fut_holding': (cmd_fut_holding, ['trade_date', 'exchange', 'fut_code']),
            'all': (cmd_all, []),
        }

        if args.command in commands:
            cmd_func, extra_attrs = commands[args.command]
            # 处理 realtime_quote 的 codes 参数
            if args.command == 'realtime_quote':
                args.ts_codes = [c.strip() for c in args.codes.split(',')]
            cmd_func(args, fetcher)
        else:
            print(f"未知命令: {args.command}")

    except ValueError as e:
        print(f"\n[FAIL] 配置错误: {e}")
        print("请确保 .env 文件中已设置 TUSHARE_TOKEN")
    except Exception as e:
        print(f"\n[FAIL] 执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
