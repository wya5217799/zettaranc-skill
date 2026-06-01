"""
免 token 数据源客户端测试（akshare / qcore 数据湖）

覆盖核心契约：
  - normalize_daily_bars：单位换算、按日期升序、pct_chg、tushare schema
  - 代码格式映射：ts_code ↔ 6 位裸码 ↔ 新浪前缀（含科创/创业/北交所边界）
  - QcoreLakeClient：从真实 parquet 读取（数据湖不存在时自动跳过）
"""

import os
from pathlib import Path

import pandas as pd
import pytest

from modules.akshare_client import (
    normalize_daily_bars,
    DAILY_SCHEMA,
    code_to_ts_code,
    ts_code_to_sina,
)


class TestNormalizeDailyBars:
    """共享规整函数：两个数据源的正确性命脉"""

    def _raw(self):
        # 故意乱序，验证函数内部会排序
        return pd.DataFrame({
            "trade_date": ["20240103", "20240101", "20240102"],
            "open": [10.5, 10.0, 10.2],
            "high": [10.8, 10.3, 10.5],
            "low": [10.4, 9.9, 10.1],
            "close": [10.6, 10.0, 10.3],
            "volume": [200_000.0, 100_000.0, 150_000.0],  # 单位：股
            "amount": [2_120_000.0, 1_000_000.0, 1_545_000.0],  # 单位：元
        })

    def test_schema_matches_tushare(self):
        out = normalize_daily_bars(self._raw(), "600487.SH")
        assert list(out.columns) == DAILY_SCHEMA

    def test_sorted_ascending(self):
        out = normalize_daily_bars(self._raw(), "600487.SH")
        assert list(out["trade_date"]) == ["20240101", "20240102", "20240103"]

    def test_unit_conversion(self):
        """vol 股÷100→手；amount 元÷1000→千元"""
        out = normalize_daily_bars(self._raw(), "600487.SH")
        first = out.iloc[0]  # 20240101
        assert first["vol"] == pytest.approx(1000.0)       # 100000 / 100
        assert first["amount"] == pytest.approx(1000.0)    # 1000000 / 1000

    def test_pct_chg_first_row_zero(self):
        out = normalize_daily_bars(self._raw(), "600487.SH")
        assert out["pct_chg"].iloc[0] == 0.0
        assert out["pre_close"].iloc[0] == out["close"].iloc[0]

    def test_pct_chg_computed(self):
        """第二天 10.3 / 10.0 - 1 = 3%"""
        out = normalize_daily_bars(self._raw(), "600487.SH")
        assert out["pct_chg"].iloc[1] == pytest.approx(3.0, abs=1e-6)
        assert out["pre_close"].iloc[1] == pytest.approx(10.0)

    def test_ts_code_filled(self):
        out = normalize_daily_bars(self._raw(), "000001.SZ")
        assert (out["ts_code"] == "000001.SZ").all()


class TestCodeToTsCode:
    """6 位裸码 → 带交易所后缀"""

    @pytest.mark.parametrize("code,expected", [
        ("600487", "600487.SH"),   # 沪主板
        ("601398", "601398.SH"),
        ("688981", "688981.SH"),   # 科创板
        ("900901", "900901.SH"),   # 沪B
        ("000001", "000001.SZ"),   # 深主板
        ("300750", "300750.SZ"),   # 创业板
        ("200011", "200011.SZ"),   # 深B
        ("830799", "830799.BJ"),   # 北交所
        ("430047", "430047.BJ"),   # 北交所
    ])
    def test_mapping(self, code, expected):
        assert code_to_ts_code(code) == expected


class TestTsCodeToSina:
    """ts_code → 新浪源带前缀"""

    @pytest.mark.parametrize("ts_code,expected", [
        ("600487.SH", "sh600487"),
        ("000001.SZ", "sz000001"),
        ("830799.BJ", "bj830799"),
        ("688981", "sh688981"),    # 无后缀按前缀推断
        ("300750", "sz300750"),
    ])
    def test_mapping(self, ts_code, expected):
        assert ts_code_to_sina(ts_code) == expected


# ─── QcoreLakeClient：依赖真实数据湖，不存在则跳过 ───────────────────────────
_LAKE_DIR = os.environ.get(
    "QCORE_DATA_DIR", str(Path.home() / "Desktop" / "量化交易" / "data")
)
_LAKE_BAR = Path(_LAKE_DIR) / "daily_bar.parquet"


@pytest.mark.skipif(
    not _LAKE_BAR.exists(), reason="qcore 数据湖不存在，跳过 QcoreLakeClient 集成测试"
)
class TestQcoreLakeClient:
    def _client(self):
        from modules.qcore_lake_client import QcoreLakeClient
        return QcoreLakeClient(data_dir=_LAKE_DIR)

    def test_get_daily_schema(self):
        df = self._client().get_daily("600487.SH", "20240101", "20240131")
        assert list(df.columns) == DAILY_SCHEMA
        assert len(df) > 0

    def test_get_daily_sorted(self):
        df = self._client().get_daily("600487.SH", "20240101", "20240131")
        assert list(df["trade_date"]) == sorted(df["trade_date"])

    def test_get_daily_date_range(self):
        df = self._client().get_daily("600487.SH", "20240101", "20240131")
        assert df["trade_date"].min() >= "20240101"
        assert df["trade_date"].max() <= "20240131"

    def test_get_stock_basic(self):
        b = self._client().get_stock_basic()
        assert list(b.columns) == [
            "ts_code", "name", "area", "industry", "market", "list_date", "is_hs"
        ]
        assert len(b) > 1000
