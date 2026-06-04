# 退役 Tushare 作为数据后端，标准化到免费源（qcore + akshare）

## 决定

日常数据后端从 Tushare（付费、需 Token + 中转 URL）切换为免费源：

- **qcore** 本地 Parquet 数据湖（日线 / 市值 / 活跃市值，秒级）为本机首选；
- **akshare** 新浪源现拉（日线）为免配置兜底；
- **Tushare（`jnb` 模式）保留但休眠** —— 代码不删，默认不推荐，留作他日接盘中实时。

## 背景与权衡

核心量化主线（60+ 指标、30+ 战法、选股、诊断、活跃市值）只消费**日线 K + 股票列表 + 市值**，免费源全部可得。Tushare 的 11 个方法中有 7 个（实时 / 资金流 / 龙虎榜 / 财务 / 涨停 / 指数 / 日历）**全项目无任何消费方**；唯一被战法消费的 `moneyflow`（大单净流入）是可选加分项。

`moneyflow` **未**接入 akshare，基于两条独立硬约束：

1. **数据源不可靠**：akshare 个股资金流走东财（`push2his.eastmoney.com`），此环境硬阻断（`RemoteDisconnected`）—— 正是项目当初把日线从东财改走新浪所规避的同一通道。
2. **单位无法验证**：战法的 5% 净流入比例阈值按 Tushare 单位（万元）标定；Tushare 退役后无法验证 akshare（元）映射的单位等价，强接会**静默扭曲** B1/B2 评分。

故 `moneyflow` 保持**优雅缺省**（LEFT JOIN 默认 0），与免费模式既有行为一致 —— 不是新的功能减法。

## 后果

- 不再需要 Tushare Token；首次引导默认推荐 akshare。
- `setup_wizard.write_env_file` 改为「合并保留」既有键，切换模式不再冲掉 `QCORE_DATA_DIR` / `TUSHARE_API_URL` / `LLM_API_KEY`。
- 战法的资金流加分项在免费模式下不触发；如未来要恢复，需接入**可靠的**个股资金流源并**重新标定阈值单位**。
- `data_sync` 中 `stk_factor` / `daily_basic` / `moneyflow` 三个 Tushare 专属步骤在免费模式下跳过（日志降级为 info，措辞改为「不影响核心功能」）。
