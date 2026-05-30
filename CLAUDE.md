# zettaranc-skill · Claude Code / AI Agent 配置

> 面向 AI 编程工具的项目上下文文件。

## 项目定位

zettaranc-skill 是一个**AI Skill（思维框架蒸馏包）+ 真实数据量化工具**的混合系统。

将 B 站 UP 主 / 前阳光私募冠军基金经理 zettaranc（万千）的投资思维框架封装为 AI 可加载的 Skill 文件（`SKILL.md`），同时提供基于真实 Tushare 行情数据的 Python 量化分析层（60+ 指标、30+ 战法、选股/回测/诊断）。

## 快速指引

| 任务 | 操作 |
|------|------|
| 安装 | `pip install -r requirements.txt` |
| 配置 | `cp .env.example .env`，填入 Tushare Token 和 API URL |
| 初始化 | `python -m modules.database` → `python -m modules.data_sync sync` |
| 分析股票 | `python -m modules.cli analyze 600487.SH` |
| 选股 | `python -m modules.cli screen --strategy B1 --limit 20` |
| 诊断持仓 | `python -m modules.cli diagnose 600487.SH` |
| 运行测试 | `python -m pytest tests/ -v`（预期 261 passed, 1 skipped） |

## 关键文件

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 核心 AI 角色扮演协议（Z 哥思维框架） |
| `README.md` | 面向人类的项目介绍 |
| `AGENTS.md` | 面向 AI 编程 Agent 的完整开发指南 |
| `docs/USER_GUIDE.md` | 详细使用手册与操作手册 |
| `docs/CHANGELOG.md` | 版本变更日志 |

## 重要约定

1. **Python 层只做数据准备**：所有点评、分析话术由 LLM 用 Z 哥角色生成，避免"AI味"
2. **数据库路径**：统一从 `DB_PATH` 环境变量读取，代码中不硬编码
3. **Tushare URL**：统一从 `TUSHARE_API_URL` 环境变量读取，代码中不硬编码
4. **模块间 DB 路径**：`modules/` 下的子模块使用 `Path(__file__).parent.parent` 解析项目根目录
5. **真实数据优先**：不使用 mock 数据，所有测试应基于真实 Tushare 数据管线
6. **最小改动原则**：修改 SKILL.md 需语料支撑，不能凭印象
