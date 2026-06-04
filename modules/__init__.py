"""
Zettaranc 技术分析模块包
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ─── 全局一次性加载 .env（包首次 import 时执行）───────────────────────────────
# 优先读取环境变量指向的路径，其次查找项目根目录的 .env
_env_path = Path(os.getenv("ZETTARANC_ENV", Path(__file__).parent.parent / ".env"))
load_dotenv(_env_path, override=False)  # 已有的环境变量不被 .env 覆盖（保持测试 fixture 隔离能力）


# ─── 控制台编码加固（包首次 import 时执行）─────────────────────────────────────
# Windows 默认控制台编码为 GBK(cp936)，无法编码 emoji / ¥ / ² 等字符。任何 print
# 这类字符会抛 UnicodeEncodeError 使命令整体崩溃（exit 1）——本项目主平台正是
# 中文 Windows，CLI 又会输出 emoji 标记，故在包级别一次性放宽 stdout/stderr 的
# 编码错误处理：**保留既有编码**（GBK 控制台下中文仍正确显示），仅把无法编码的
# 字符降级为 'replace' 而非抛异常。这是“崩溃类”问题的单点根治。
def _relax_stream_errors(stream) -> None:
    """放宽单个文本流的编码错误处理为 'replace'（保留其既有编码）。"""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:  # 非 TextIOWrapper（已被替换/分离）—— 跳过
        return
    try:
        reconfigure(errors="replace")
    except (ValueError, OSError, AttributeError):
        # 流不支持重配置（如已写入且实现受限）时静默跳过，不影响功能
        pass


def _configure_console() -> None:
    """包首次 import 时加固 stdout/stderr，避免控制台编码崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            _relax_stream_errors(stream)


_configure_console()


# ─── 公开 API ────────────────────────────────────────────────────────────────
from .database import get_connection, get_db_path, init_database
from .tushare_client import TushareClient
from .setup_wizard import run_wizard, check_env_exists, check_data_mode

# 随堂测试复盘模块（数据准备层，点评由LLM生成）
from .trade_parser import TradeParser, ParseResult, format_trade_for_review
from .trade_manager import TradeManager, trade_manager
from .trade_reviewer import TradeReviewer, ReviewContext, create_reviewer

__all__ = [
    # 数据库
    'get_connection',
    'get_db_path',
    'init_database',
    # Tushare
    'TushareClient',
    # 初始化向导
    'run_wizard',
    'check_env_exists',
    'check_data_mode',
    # 随堂测试复盘（数据层）
    'TradeParser',
    'ParseResult',
    'format_trade_for_review',
    'TradeManager',
    'trade_manager',
    'TradeReviewer',
    'ReviewContext',
    'create_reviewer',
]


def get_data_mode() -> str:
    """获取当前数据模式：jnb 或 websearch"""
    return os.getenv("DATA_MODE", "websearch")


def get_project_root() -> Path:
    """获取项目根目录（modules/ 的上一级）"""
    return Path(__file__).parent.parent
