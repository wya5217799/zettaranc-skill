"""
Akshare 数据客户端（免 token，走 akshare 公开数据源）

设计目标：作为 TushareClient 的「可替换数据源」，所有返回的 DataFrame
列名、单位、格式与 Tushare 完全对齐，使下游 data_sync / 指标 / 战法
无需任何改动即可工作。

单位对齐（关键）：
  - akshare stock_zh_a_daily: volume 单位「股」、amount 单位「元」
  - tushare daily/pro_bar:     vol    单位「手」、amount 单位「千元」
  => vol = volume / 100, amount = amount / 1000

数据源说明：
  - 日线走新浪源 stock_zh_a_daily(adjust='qfq')，前复权，绕开东财代理拦截
  - 股票列表走 stock_info_a_code_name
"""

import time
import logging
from typing import Optional

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print("请先安装依赖: pip install akshare pandas")

logger = logging.getLogger(__name__)


def ts_code_to_sina(ts_code: str) -> str:
    """Tushare 代码 → 新浪源带前缀代码

    '600487.SH' -> 'sh600487'，'000001.SZ' -> 'sz000001'，'830799.BJ' -> 'bj830799'
    无后缀时按代码前缀推断。
    """
    code, _, market = ts_code.partition(".")
    m = market.upper()
    if m == "SH":
        return f"sh{code}"
    if m == "SZ":
        return f"sz{code}"
    if m == "BJ":
        return f"bj{code}"
    # 无后缀：按前缀推断
    if code.startswith(("60", "68", "9")):
        return f"sh{code}"
    if code.startswith(("00", "30", "20")):
        return f"sz{code}"
    if code.startswith(("8", "4")):
        return f"bj{code}"
    return f"sh{code}"


def code_to_ts_code(code: str) -> str:
    """6 位裸代码 → Tushare 代码（带交易所后缀）

    6xx/9xx -> .SH，0xx/2xx/3xx -> .SZ，4xx/8xx -> .BJ
    """
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    if code.startswith(("8", "4")):
        return f"{code}.BJ"
    return f"{code}.SH"


def _market_label(ts_code: str) -> str:
    """按板块推断 market 字段（主板/创业板/科创板/北交所）"""
    code = ts_code.split(".")[0]
    if code.startswith("688"):
        return "科创板"
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith(("8", "4")):
        return "北交所"
    return "主板"


# Tushare pro_bar 日线列契约（akshare / qcore 两个数据源共用）
DAILY_SCHEMA = [
    "ts_code", "trade_date", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "vol", "amount",
]

# Tushare stock_basic 列契约（akshare / qcore 两个数据源共用）
STOCK_BASIC_SCHEMA = [
    "ts_code", "name", "area", "industry", "market", "list_date", "is_hs",
]


def build_stock_basic(src: "pd.DataFrame") -> "pd.DataFrame":
    """把 (code, name) 源表规整为 Tushare stock_basic schema（akshare / qcore 共用）。

    免费数据源仅有 code/name：area/industry/list_date/is_hs 留空（下游 fillna），
    market 按板块前缀推断。抽成单一函数，避免两个 client 的列构造逻辑漂移。
    """
    if src is None or src.empty:
        return pd.DataFrame(columns=STOCK_BASIC_SCHEMA)
    out = pd.DataFrame()
    out["ts_code"] = src["code"].astype(str).map(code_to_ts_code)
    out["name"] = src["name"] if "name" in src.columns else ""
    out["area"] = ""
    out["industry"] = ""
    out["market"] = out["ts_code"].map(_market_label)
    out["list_date"] = ""
    out["is_hs"] = ""
    return out[STOCK_BASIC_SCHEMA]


def normalize_daily_bars(df: "pd.DataFrame", ts_code: str) -> "pd.DataFrame":
    """把原始日线规整为 Tushare pro_bar schema（akshare / qcore 共用）。

    入参 df 需已含: trade_date(YYYYMMDD 字符串)、open/high/low/close、
    volume(单位「股」)、amount(单位「元」)。
    处理: 按 trade_date 升序 → 单位换算(vol÷100→手, amount÷1000→千元)
          → 按前复权收盘价算 pct_chg/change/pre_close(首行置 0)。
    抽成单一函数，避免两个 client 的换算逻辑各自漂移。
    """
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["ts_code"] = ts_code
    df["vol"] = df["volume"] / 100.0
    df["amount"] = df["amount"] / 1000.0
    df["pre_close"] = df["close"].shift(1)
    df["change"] = (df["close"] - df["pre_close"]).round(4).fillna(0.0)
    df["pct_chg"] = ((df["close"] / df["pre_close"] - 1) * 100).round(4).fillna(0.0)
    df["pre_close"] = df["pre_close"].fillna(df["close"])
    return df[DAILY_SCHEMA].reset_index(drop=True)


class AkshareClient:
    """Akshare 数据客户端（接口与 TushareClient 对齐）

    实现的方法：
      - get_stock_basic: 股票列表（ts_code, name, area, industry, market, list_date, is_hs）
      - get_daily:       个股日线前复权（tushare pro_bar schema）
    """

    def __init__(self, min_request_interval: float = 0.25):
        self.min_request_interval = min_request_interval
        self.last_request_time = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    # ==================== 股票基础信息 ====================

    def get_stock_basic(self) -> pd.DataFrame:
        """全市场 A 股列表

        返回列与 Tushare stock_basic 对齐：
        ts_code, name, area, industry, market, list_date, is_hs
        akshare 仅提供 code/name，其余字段以板块推断或留空，
        下游 data_sync 会 .fillna('')，不影响入库与核心分析。
        """
        return build_stock_basic(ak.stock_info_a_code_name())  # 源列: code, name

    # ==================== 日线行情 ====================

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """个股日线（前复权），返回 Tushare pro_bar schema

        列: ts_code, trade_date, open, high, low, close, pre_close,
            change, pct_chg, vol, amount
        - trade_date: YYYYMMDD 字符串
        - vol: 手（akshare 股 ÷ 100）
        - amount: 千元（akshare 元 ÷ 1000）
        - pct_chg: 百分比，按前复权收盘价计算
        """
        self._rate_limit()
        sym = ts_code_to_sina(ts_code)
        try:
            df = ak.stock_zh_a_daily(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
        except Exception as e:
            logger.error(f"akshare 日线获取失败 {ts_code} ({sym}): {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
        return normalize_daily_bars(df, ts_code)

    def check_connection(self) -> bool:
        """连通性检查：能否取到股票列表"""
        try:
            df = ak.stock_info_a_code_name()
            return df is not None and len(df) > 0
        except Exception:
            return False
