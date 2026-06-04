"""
启动向导模块
用户首次使用时引导配置数据源：
  - akshare  免 token 现拉（推荐默认）
  - qcore    本机 Parquet 数据湖（最快）
  - jnb      走 Tushare API（休眠保留，需 Token）
  - websearch 普通小万（纯对话，不跑数据）
"""

import os
from pathlib import Path
from typing import Optional

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）

# 数据模式别名
MODE_JNB = "jnb"           # JNB 模式：走 Tushare API（休眠保留）
MODE_NORMAL = "websearch"  # 普通小万模式：走网络搜索
MODE_AKSHARE = "akshare"   # akshare 免 token 现拉
MODE_QCORE = "qcore"       # 本机 Parquet 数据湖
MODE_NAMES = {
    MODE_JNB: "JNB",
    MODE_NORMAL: "普通小万",
    MODE_AKSHARE: "akshare",
    MODE_QCORE: "qcore",
}


def check_env_exists() -> bool:
    """检查 .env 文件是否存在且包含有效配置"""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return False

    # 检查是否有有效的 token（不是占位符）
    token = os.environ.get("TUSHARE_TOKEN", "")
    data_mode = os.environ.get("DATA_MODE", "")
    return bool(token) and "你的" not in token and data_mode != ""


def check_data_mode() -> Optional[str]:
    """返回当前数据模式：qcore / akshare / jnb / websearch / None（未配置）"""
    return os.environ.get("DATA_MODE", None)


def get_mode_display_name(mode: str) -> str:
    """获取模式显示名称"""
    return MODE_NAMES.get(mode, mode)


def write_env_file(token: Optional[str] = None, mode: str = MODE_NORMAL,
                   env_path: Optional[Path] = None) -> str:
    """
    写入 .env 文件

    Args:
        token: Tushare Token，免 token 模式下可为 None
        mode: 数据模式，qcore / akshare / jnb / websearch
        env_path: 目标 .env 路径，默认写入项目根目录。测试中应传入临时路径
                  以避免覆盖用户真实的 .env 配置

    Returns:
        .env 文件的绝对路径

    Note:
        采用「合并保留」策略 —— 读取既有 .env 的所有键，仅更新 DATA_MODE
        （及可选 TUSHARE_TOKEN），其余键（QCORE_DATA_DIR、TUSHARE_API_URL、
        LLM_API_KEY 等）原样保留，避免切换模式时把别的配置冲掉。
    """
    if env_path is None:
        env_path = Path(__file__).parent.parent / ".env"
    else:
        env_path = Path(env_path)

    # 0) 校验模式合法，避免打错字静默写坏 .env
    if mode not in MODE_NAMES:
        raise ValueError(f"未知数据模式: {mode!r}，应为 {list(MODE_NAMES)} 之一")

    updates = {"DATA_MODE": mode}
    if token:
        updates["TUSHARE_TOKEN"] = token

    # 1) 逐行「原样保留 + 就地替换」：注释、空行、键顺序全部保留，
    #    只改命中的键，避免把 QCORE_DATA_DIR / 中转 URL / LLM Key 及其注释冲掉。
    old_lines = (
        env_path.read_text(encoding="utf-8").splitlines()
        if env_path.exists() else []
    )
    out: list[str] = []
    for raw in old_lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                continue
        out.append(raw)

    # 2) 文件中尚不存在的键追加到末尾（含必要默认值）
    tail = dict(updates)
    tail.setdefault("DATA_DIR", "data")
    tail.setdefault("DB_PATH", "data/stock_data.db")
    present = {
        ln.split("=", 1)[0].strip()
        for ln in out
        if "=" in ln and not ln.strip().startswith("#")
    }
    for key, value in tail.items():
        if key not in present:
            out.append(f"{key}={value}")

    # 3) 全新文件加一行模式说明头
    if not old_lines:
        out.insert(0, "# 数据模式: qcore(数据湖) / akshare(免token现拉) / jnb(Tushare) / websearch(普通小万)")

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    # 4) 同步进程环境变量，使当前会话立即生效
    os.environ["DATA_MODE"] = mode
    if token:
        os.environ["TUSHARE_TOKEN"] = token

    return str(env_path)


def test_jnb_connection(token: str) -> bool:
    """
    测试 JNB(Tushare) 连通性

    Returns:
        True 表示连接成功
    """
    from .tushare_client import TushareClient

    try:
        client = TushareClient(token=token)
        return client.check_connection()
    except Exception as e:
        print(f"  连接测试失败: {e}")
        return False


def run_wizard():
    """
    运行启动向导（命令行模式，agent 对话中不直接使用）

    流程：
    1. 检查是否已配置
    2. 询问用户选择数据模式
    3. 如选 JNB，收集 Token 并测试连通性
    4. 写入 .env 并确认
    """
    print("=" * 50)
    print("  Zettaranc 启动向导")
    print("=" * 50)
    print()

    # 检查是否已配置
    if check_env_exists():
        mode = check_data_mode()
        display = get_mode_display_name(mode)
        print(f"[已配置] 当前模式: {display}")
        print()
        print("如需重新配置，请删除 .env 文件后重新运行")
        return mode

    print("欢迎使用 Zettaranc！请选择模式：")
    print()
    print("  [1] JNB — 走 Tushare API（需要 Token，指标全开）")
    print("  [2] 普通小万 — 走网络搜索（不用配，开箱即用）")
    print()

    while True:
        choice = input("请选择 [1/2]: ").strip()
        if choice in ("1", "2"):
            break
        print("  请输入 1 或 2")

    if choice == "1":
        # ====== JNB 模式 ======
        print()
        print("请输入你的 Tushare Token（56位）")
        print("  获取地址：https://tushare.pro/user/token")
        print()

        while True:
            token = input("Token: ").strip()
            if len(token) >= 30:
                break
            print("  Token 长度不够，请重新输入")

        print()
        print("正在测试连通性...")
        if test_jnb_connection(token):
            print("  连接测试通过！")
            env_path = write_env_file(token=token, mode=MODE_JNB)
            print(f"  配置已写入: {env_path}")
            print()
            print("JNB 模式已启用")
            return MODE_JNB
        else:
            print("  连接测试失败")
            print()
            retry = input("是否重试？[y/n]: ").strip().lower()
            if retry == "y":
                os.environ.pop("TUSHARE_TOKEN", None)
                return run_wizard()
            else:
                print("已切换至普通小万模式")
                env_path = write_env_file(mode=MODE_NORMAL)
                print(f"配置已写入: {env_path}")
                return MODE_NORMAL

    else:
        # ====== 普通小万 模式 ======
        print()
        env_path = write_env_file(mode=MODE_NORMAL)
        print(f"配置已写入: {env_path}")
        print("普通小万模式已启用")
        return MODE_NORMAL


if __name__ == "__main__":
    mode = run_wizard()
    print(f"\n最终模式: {get_mode_display_name(mode)}")
