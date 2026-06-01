"""
Qcore 数据湖客户端（读取 qcore 项目沉淀的 Parquet 数据湖，免 token、离线、7年历史）

设计目标：与 AkshareClient / TushareClient 接口一致，返回的 DataFrame
列名、单位、格式与 Tushare 完全对齐，下游 data_sync / 指标 / 战法 零改动。

为什么能薄集成：
  qcore 的 daily_bar.parquet 本身就是 akshare(stock_zh_a_daily, qfq)落盘，
  列名 code/date/open/high/low/close/volume/amount/... 与 akshare 完全相同。
  因此沿用 AkshareClient 同款「单位换算 + code→ts_code」翻译逻辑即可。

数据源（QCORE_DATA_DIR 指向 qcore 项目的 data/ 目录）：
  - daily_bar.parquet   全 A 前复权日线（~8M 行 / 5000+ 股 / 2019~今）
  - stock_info.parquet  股票列表（code, name）

依赖：仅 pandas + pyarrow（谓词下推按 code 读取，单只 ~0.2s），不引入 polars。
"""

import os
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

try:
    import pandas as pd
except ImportError:
    print("请先安装依赖: pip install pandas pyarrow")

from .akshare_client import normalize_daily_bars, build_stock_basic

logger = logging.getLogger(__name__)


def _default_qcore_data_dir() -> str:
    """默认 qcore 数据湖目录（可被 QCORE_DATA_DIR 环境变量覆盖）"""
    return os.environ.get(
        "QCORE_DATA_DIR",
        str(Path.home() / "Desktop" / "量化交易" / "data"),
    )


class QcoreLakeClient:
    """Qcore Parquet 数据湖客户端（接口与 TushareClient / AkshareClient 对齐）

    实现的方法：
      - get_stock_basic: 股票列表（ts_code, name, area, industry, market, list_date, is_hs）
      - get_daily:       个股日线前复权（tushare pro_bar schema）
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or _default_qcore_data_dir())
        self.daily_bar_path = self.data_dir / "daily_bar.parquet"
        self.stock_info_path = self.data_dir / "stock_info.parquet"
        if not self.daily_bar_path.exists():
            raise FileNotFoundError(
                f"未找到 qcore 数据湖日线文件: {self.daily_bar_path}\n"
                f"请在 .env 设置 QCORE_DATA_DIR 指向 qcore 项目的 data/ 目录。"
            )
        # 懒加载的「按 code 分组」缓存。daily_bar.parquet 按 date 排序，
        # 每个 row group 的 code 统计范围都覆盖全市场，谓词下推无法跳过任何
        # row group —— 逐只 read_parquet(filters=) 会退化为全表扫(~156ms/只)。
        # 故首次访问时全量读一次并按 code 分组，后续切片≈0ms。
        # 批量同步 5000+ 只: 810s → ~3s。代价是同步期间约 1.3GB 内存。
        self._code_groups: Optional[Dict[str, "pd.DataFrame"]] = None
        self._groups_lock = threading.Lock()

    def _get_code_groups(self) -> Dict[str, "pd.DataFrame"]:
        """全量读 daily_bar 一次并按 code 分组（双检锁，线程安全）。"""
        if self._code_groups is None:
            with self._groups_lock:
                if self._code_groups is None:  # 双重检查，避免并发重复加载
                    full = pd.read_parquet(self.daily_bar_path)
                    # date → YYYYMMDD 字符串：用整数算术而非 strftime
                    # （8M 行上 strftime 约 17s，整数算术约 2s，结果一致）
                    _dt = pd.to_datetime(full["date"])
                    full["trade_date"] = (
                        _dt.dt.year * 10000 + _dt.dt.month * 100 + _dt.dt.day
                    ).astype(str)
                    self._code_groups = {
                        code: g for code, g in full.groupby("code")
                    }
        return self._code_groups

    # ==================== 股票基础信息 ====================

    def get_stock_basic(self) -> pd.DataFrame:
        """全市场 A 股列表，列对齐 Tushare stock_basic

        ts_code, name, area, industry, market, list_date, is_hs
        qcore stock_info 仅含 code/name，其余以板块推断或留空（下游会 fillna）。
        """
        if self.stock_info_path.exists():
            src = pd.read_parquet(self.stock_info_path)  # code, name
        else:
            # 退化：从日线文件抽取去重 code
            codes = pd.read_parquet(self.daily_bar_path, columns=["code"])["code"].unique()
            src = pd.DataFrame({"code": codes, "name": ""})
        return build_stock_basic(src)

    # ==================== 日线行情 ====================

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """个股日线（前复权），返回 Tushare pro_bar schema

        列: ts_code, trade_date, open, high, low, close, pre_close,
            change, pct_chg, vol, amount
        - trade_date: YYYYMMDD 字符串
        - vol: 手（数据湖单位「股」÷ 100）
        - amount: 千元（数据湖单位「元」÷ 1000）
        - pct_chg: 百分比，按前复权收盘价计算（已按日期升序）
        """
        code = ts_code.split(".")[0]  # 6 位裸代码
        try:
            df = self._get_code_groups().get(code)
        except Exception as e:
            logger.error(f"qcore 数据湖读取失败 {ts_code} (code={code}): {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # 日期区间过滤（trade_date 已在缓存中预计算为 YYYYMMDD 字符串）
        df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)]
        if df.empty:
            return pd.DataFrame()
        # 规整为 tushare schema（内部会按 trade_date 升序后算 pct_chg）
        return normalize_daily_bars(df, ts_code)

    def check_connection(self) -> bool:
        """连通性检查：数据湖日线文件是否可读"""
        try:
            df = pd.read_parquet(self.daily_bar_path, columns=["code"], filters=[("code", "==", "600487")])
            return df is not None and len(df) > 0
        except Exception:
            return False
