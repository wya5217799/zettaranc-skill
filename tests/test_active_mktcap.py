"""活跃市值读取器测试（modules/active_mktcap.py）。

遵循项目「真实数据优先」原则：happy path 直接读真实数据湖文件，
文件不存在时跳过；同时覆盖「文件缺失」的优雅降级路径。
"""
import importlib

import pytest

active_mktcap = importlib.import_module("modules.active_mktcap")
get_active_mktcap = active_mktcap.get_active_mktcap
format_active_mktcap = active_mktcap.format_active_mktcap
ActiveMktcapReading = active_mktcap.ActiveMktcapReading


def _real_file_exists() -> bool:
    return (active_mktcap._resolve_data_dir() / active_mktcap.ACTIVE_MKTCAP_FILE).exists()


def test_missing_file_degrades_gracefully(tmp_path, monkeypatch):
    """QCORE_DATA_DIR 指向空目录时，应返回 available=False 且带原因，不抛异常。"""
    monkeypatch.setenv("QCORE_DATA_DIR", str(tmp_path))
    reading = get_active_mktcap(days=30)
    assert reading.available is False
    assert reading.reason
    assert reading.latest_value == 0.0


def test_format_unavailable_reading():
    reading = ActiveMktcapReading(available=False, reason="测试原因")
    text = format_active_mktcap(reading)
    assert "不可用" in text
    assert "测试原因" in text


def test_malformed_file_missing_date_column_degrades(tmp_path, monkeypatch):
    """parquet 有 active_mktcap 列但缺 date 列时，必须优雅降级而非抛 KeyError。

    回归点：守卫原先只校验 active_mktcap 列，随后 df.sort_values('date')
    会对缺列文件抛未捕获的 KeyError，违反「读取失败统一降级」契约。
    """
    import pandas as pd
    bad = tmp_path / active_mktcap.ACTIVE_MKTCAP_FILE
    pd.DataFrame({"active_mktcap": [1.0, 2.0, 3.0]}).to_parquet(bad)
    monkeypatch.setenv("QCORE_DATA_DIR", str(tmp_path))

    reading = get_active_mktcap(days=30)  # 不应抛异常
    assert reading.available is False
    assert reading.reason


@pytest.mark.skipif(not _real_file_exists(), reason="真实活跃市值数据湖文件不存在")
def test_real_reading_happy_path():
    reading = get_active_mktcap(days=60)
    assert reading.available is True
    assert reading.latest_value > 0
    assert reading.latest_date  # YYYY-MM-DD
    # 窗口按日期升序，最后一个即最新
    assert len(reading.recent) > 1
    dates = [p.date for p in reading.recent]
    assert dates == sorted(dates)
    assert reading.recent[-1].value == reading.latest_value
    # 高点应 >= 最新值（窗口内取 max）
    assert reading.peak_value >= reading.latest_value


@pytest.mark.skipif(not _real_file_exists(), reason="真实活跃市值数据湖文件不存在")
def test_real_format_contains_data():
    reading = get_active_mktcap(days=30)
    text = format_active_mktcap(reading, tail=5)
    assert "活跃市值" in text
    assert reading.latest_date in text
