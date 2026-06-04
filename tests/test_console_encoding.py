"""
回归测试：控制台编码加固

Bug（已修）：Windows 默认控制台编码为 GBK(cp936)，无法编码 emoji / ¥ / ² 等字符。
CLI 输出 emoji 标记（如 cmd_analyze 的紧急/机会/观察分组）时，print 会抛
UnicodeEncodeError 使命令整体崩溃（exit 1）——本项目主平台正是中文 Windows。

修复：modules 包首次 import 时把 stdout/stderr 的编码错误处理放宽为 'replace'
（保留既有编码，GBK 控制台下中文仍正确），从根上消除“崩溃类”问题；同时把 CLI
直接输出的 emoji 换成 GBK 安全的方括号标记（[紧急]/[机会]/[观察]/[!]/[OK]）。

下面用“强制 GBK 的子进程打印问题字符”这一忠实可移植的复现作为回归锁。
"""

import io
import os
import subprocess
import sys

# 覆盖项目中出现过的全部非 GBK 字符：emoji + 警告/对勾 + 半角¥ + 上标²
_PROBLEM_CHARS = "\U0001f534\U0001f7e2⚪⚠️✅\xa5\xb2"
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRelaxStreamErrors:
    """单元：_relax_stream_errors 让流在遇到不可编码字符时降级而非抛异常。"""

    def test_strict_gbk_stream_raises_before_relax(self):
        """前提：默认 strict 的 GBK 流写入 emoji 必抛 UnicodeEncodeError。"""
        stream = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
        try:
            import pytest
            with pytest.raises(UnicodeEncodeError):
                stream.write(_PROBLEM_CHARS)
                stream.flush()
        finally:
            stream.detach()

    def test_relax_makes_unencodable_safe(self):
        """放宽后：同一 GBK 流写入全部问题字符不再抛异常，且编码仍为 gbk。"""
        from modules import _relax_stream_errors

        stream = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
        try:
            _relax_stream_errors(stream)
            stream.write(_PROBLEM_CHARS)   # 不应抛异常
            stream.flush()
            assert stream.encoding.lower() == "gbk"   # 编码被保留（中文仍正确）
        finally:
            stream.detach()

    def test_relax_is_safe_on_non_reconfigurable_stream(self):
        """流不支持 reconfigure（如普通对象）时静默跳过，不抛异常。"""
        from modules import _relax_stream_errors

        class _Dummy:
            pass

        _relax_stream_errors(_Dummy())  # 不应抛异常


class TestImportHardensConsole:
    """集成：在强制 GBK 的子进程中 import 包并 print 问题字符，不得崩溃。"""

    def _run(self, code: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONIOENCODING="gbk")
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )

    def test_import_modules_then_print_emoji_exits_zero(self):
        code = "import modules; print('%s')" % _PROBLEM_CHARS
        proc = self._run(code)
        assert proc.returncode == 0, proc.stderr
        assert "UnicodeEncodeError" not in proc.stderr

    def test_without_import_baseline_crashes(self):
        """对照：不 import 包（不加固）时，同样的打印在 GBK 下崩溃 —— 证明是加固生效。"""
        code = "print('%s')" % _PROBLEM_CHARS
        proc = self._run(code)
        assert proc.returncode != 0
        assert "UnicodeEncodeError" in proc.stderr


class TestCmdAnalyzeOnGbkConsole:
    """端到端（最贴近用户原始崩溃的 seam）：`analyze` 命中 CRITICAL 信号时，
    cli.py 紧急分组分支在 GBK 控制台下不得崩溃，且中文/标记正确（非 emoji、非 '?'）。"""

    def _gbk_stdout(self):
        import io
        return io.TextIOWrapper(io.BytesIO(), encoding="gbk", newline="")

    def test_analyze_does_not_crash_on_critical_signal(self, db_conn, monkeypatch):
        import modules.cli as cli
        from tests.conftest import (
            generate_downtrend_klines, write_klines_to_db, write_stock_basic,
        )
        from modules.strategies.core import StrategySignal, StrategyType, Priority

        ts = "600519.SH"
        write_stock_basic(db_conn, ts_code=ts)
        write_klines_to_db(
            db_conn,
            generate_downtrend_klines(n=150, ts_code=ts, start_date="20250101"),
        )

        # 注入 CRITICAL 信号 → 确定性命中 cli.py 的紧急分组分支（真实数据不保证产出）
        def fake_detect(ts_code, days=120):
            return [StrategySignal(
                ts_code=ts_code, trade_date="20250520",
                strategy=StrategyType.S1, confidence=0.9,
                description="丑陋大绿帽，初级逃顶", priority=Priority.CRITICAL,
            )]
        monkeypatch.setattr("modules.strategies.detect_all_strategies", fake_detect)

        # 模拟中文 Windows：GBK 起源的 stdout + 真实命令行入口
        monkeypatch.setattr(sys, "argv", ["modules.cli", "analyze", ts, "--days", "120"])
        gbk = self._gbk_stdout()
        monkeypatch.setattr(sys, "stdout", gbk)

        cli.main()   # main() 在入口加固 stdout；含紧急分组的输出不得抛 UnicodeEncodeError
        gbk.flush()

        # GBK 起源的流 → 按 gbk 解码（修复保留既有编码，中文正确）
        out = gbk.buffer.getvalue().decode("gbk", errors="replace")
        assert "[紧急]" in out          # 走到了紧急分组分支，且用的是 GBK 安全标记
        assert "丑陋大绿帽" in out       # 中文正常（未 mojibake）
        assert "\U0001f534" not in out   # 不再有 emoji（已换成方括号标记）
        assert "�" not in out       # 也不应出现替换符（中文/标记均 GBK 可编码）
