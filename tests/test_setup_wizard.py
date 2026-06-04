"""
setup_wizard.py 配置测试
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from modules.setup_wizard import (
    check_env_exists, check_data_mode, write_env_file,
    get_mode_display_name, MODE_JNB, MODE_NORMAL, MODE_AKSHARE, MODE_QCORE
)


class TestCheckEnvExists:
    def test_no_env_not_configured(self):
        # 清除环境变量
        for key in ("TUSHARE_TOKEN", "DATA_MODE"):
            if key in os.environ:
                del os.environ[key]
        assert check_env_exists() is False


class TestWriteEnvFile:
    def test_write_websearch_mode(self, tmp_path):
        """写普通小万模式（写入临时路径，避免覆盖项目根 .env）"""
        # 先清除已有的 DATA_MODE
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]

        path = write_env_file(mode=MODE_NORMAL, env_path=tmp_path / ".env")
        assert Path(path).exists()
        assert os.environ.get("DATA_MODE") == MODE_NORMAL

        content = Path(path).read_text(encoding="utf-8")
        assert "DATA_MODE=websearch" in content

    def test_write_jnb_mode(self, tmp_path):
        """写 JNB 模式（写入临时路径，避免覆盖项目根 .env）"""
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]
        if "TUSHARE_TOKEN" in os.environ:
            del os.environ["TUSHARE_TOKEN"]

        path = write_env_file(token="test_token_12345", mode=MODE_JNB,
                              env_path=tmp_path / ".env")
        assert Path(path).exists()
        assert os.environ.get("DATA_MODE") == MODE_JNB
        assert os.environ.get("TUSHARE_TOKEN") == "test_token_12345"

        content = Path(path).read_text(encoding="utf-8")
        assert "DATA_MODE=jnb" in content
        assert "TUSHARE_TOKEN=test_token_12345" in content

    def test_write_akshare_mode(self, tmp_path):
        """写 akshare 免 token 模式"""
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]
        path = write_env_file(mode=MODE_AKSHARE, env_path=tmp_path / ".env")
        assert os.environ.get("DATA_MODE") == MODE_AKSHARE
        assert "DATA_MODE=akshare" in Path(path).read_text(encoding="utf-8")

    def test_preserves_existing_keys(self, tmp_path):
        """切换模式时必须保留既有键（QCORE_DATA_DIR / LLM_API_KEY 等不被冲掉）。

        这是 write_env_file 旧实现的回归点：原先整体重写 .env 会丢失
        qcore / Tushare 中转 / LLM 等配置。
        """
        env = tmp_path / ".env"
        env.write_text(
            "DATA_MODE=qcore\n"
            "QCORE_DATA_DIR=/path/to/lake\n"
            "TUSHARE_API_URL=https://tt.example.cn\n"
            "LLM_API_KEY=sk-test-keep-me\n",
            encoding="utf-8",
        )
        write_env_file(mode=MODE_AKSHARE, env_path=env)
        content = env.read_text(encoding="utf-8")
        assert "DATA_MODE=akshare" in content
        assert "QCORE_DATA_DIR=/path/to/lake" in content
        assert "TUSHARE_API_URL=https://tt.example.cn" in content
        assert "LLM_API_KEY=sk-test-keep-me" in content

    def test_preserves_comments_and_order(self, tmp_path):
        """逐行就地替换：用户注释与键顺序必须保留，仅 DATA_MODE 被改。"""
        env = tmp_path / ".env"
        env.write_text(
            "# 我的私有注释\n"
            "DATA_MODE=qcore\n"
            "# qcore 目录说明\n"
            "QCORE_DATA_DIR=/lake\n",
            encoding="utf-8",
        )
        write_env_file(mode=MODE_AKSHARE, env_path=env)
        content = env.read_text(encoding="utf-8")
        assert "# 我的私有注释" in content
        assert "# qcore 目录说明" in content
        assert "DATA_MODE=akshare" in content
        assert "QCORE_DATA_DIR=/lake" in content
        # DATA_MODE 不应被重复写入
        assert content.count("DATA_MODE=") == 1

    def test_invalid_mode_raises(self, tmp_path):
        """打错字的模式应抛 ValueError，而非静默写坏 .env。"""
        with pytest.raises(ValueError):
            write_env_file(mode="aksahre", env_path=tmp_path / ".env")


class TestCheckDataMode:
    def test_returns_mode(self):
        os.environ["DATA_MODE"] = "websearch"
        assert check_data_mode() == "websearch"

    def test_returns_none_if_not_set(self):
        if "DATA_MODE" in os.environ:
            del os.environ["DATA_MODE"]
        # 新进程可能没有设置
        mode = check_data_mode()
        assert mode is None or mode in ("websearch", "jnb")


class TestGetModeDisplayName:
    def test_jnb(self):
        assert get_mode_display_name(MODE_JNB) == "JNB"

    def test_normal(self):
        assert get_mode_display_name(MODE_NORMAL) == "普通小万"

    def test_unknown(self):
        assert get_mode_display_name("unknown") == "unknown"
