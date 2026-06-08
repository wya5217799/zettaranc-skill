"""
TradeParser 解析与确认/纠错测试

重点覆盖 confirm_and_fill 的纠错路径（此前为未实现的空桩）：
- 确认 → 原样返回
- 否定 + 修正 → 重新解析并覆盖真正提取到的字段
- 「不对」不被误判为确认（虽含「对」）
- 解析器默认值（如默认 trade_date）不污染原数据
- 不修改入参（不可变更新）
"""

from modules.trade_parser import TradeParser


def _base_record() -> dict:
    return {
        'trade_date': '2026-01-01',
        'ts_code': '600519.SH',
        'name': '茅台',
        'action': 'BUY',
        'price': 10.0,
        'quantity': 100,
    }


def test_confirm_returns_data_unchanged():
    parser = TradeParser()
    data = _base_record()
    result = parser.confirm_and_fill(data, "对")
    assert result == data


def test_deny_with_price_correction_updates_only_price():
    parser = TradeParser()
    data = _base_record()
    result = parser.confirm_and_fill(data, "不对，单价 12.5 元")
    assert result['price'] == 12.5
    # 其余字段保持
    assert result['ts_code'] == '600519.SH'
    assert result['quantity'] == 100
    assert result['action'] == 'BUY'


def test_buduidui_not_treated_as_confirm():
    """「不对」含「对」，必须按否定处理并应用修正，而非原样返回。"""
    parser = TradeParser()
    data = _base_record()  # price=10
    result = parser.confirm_and_fill(data, "不对，价格 20 元")
    assert result['price'] == 20.0  # 若误判为确认会停在 10


def test_default_trade_date_does_not_clobber_original():
    """修正回复未提日期时，解析器默认的今日日期不应覆盖原有日期。"""
    parser = TradeParser()
    data = _base_record()  # trade_date=2026-01-01
    result = parser.confirm_and_fill(data, "卖出 500 股")
    assert result['trade_date'] == '2026-01-01'  # 原日期保留
    assert result['action'] == 'SELL'            # 提取到的覆盖
    assert result['quantity'] == 500


def test_confirm_and_fill_does_not_mutate_input():
    parser = TradeParser()
    data = _base_record()
    snapshot = dict(data)
    parser.confirm_and_fill(data, "不对，价格 20 元")
    assert data == snapshot  # 入参未被修改


def test_pure_deny_without_correction_returns_data():
    parser = TradeParser()
    data = _base_record()
    result = parser.confirm_and_fill(data, "不对")
    # 无可提取的修正值 → 维持原数据
    assert result['price'] == 10.0
    assert result['ts_code'] == '600519.SH'
