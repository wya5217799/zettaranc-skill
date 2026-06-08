# zettaranc-skill

一个「思维框架蒸馏包」(SKILL.md 里的 Z 哥人格) + 真实数据量化层(modules/),后者用免费 A 股数据为人格提供指标、战法、选股与诊断的原料。

## Language

### Mode(模式 —— 决定 AI 能做什么)

**JNB Mode**:
全功能、有数据支撑的模式 —— analyze / screen / diagnose / 交割单复盘 / 看公司 全部可跑。名字源于早期「Tushare 驱动」,但数据后端正被免费源(qcore + akshare)替代;**名字与功能集不变**。
_Avoid_: 「Tushare 模式」(后端已不由 Tushare 定义)

**普通小万 Mode**(`websearch`):
纯对话模式 —— 只聊 Z 哥框架,无行情、无指标。
_Avoid_: 「正常模式」「demo 模式」

### Source(数据源 —— 决定数据从哪来,与 Mode 正交)

**qcore(数据湖)**:
本地 Parquet 湖(`量化交易/data` 目录),7 年历史、免 token、秒级。其日线本质是 akshare(qfq) 落盘,故 **qcore 与 akshare 同源**。
_Avoid_: 说「qcore 模式」时其实指的是 Source

**akshare(现拉)**:
按需从公开源(新浪/东财)免费拉取。单次较慢,但能供给湖里没有的数据(如个股**大单净流入**)。

**Tushare**:
付费/token API。**正作为数据后端退役** —— 难配置,且免费源已覆盖所有被消费的字段。
_Avoid_: 把 Tushare 当成任何功能的必需项

### 数据内容术语

**活跃市值**:
全市场概率标尺(非选股工具)—— +4%=多头建仓,-2.3%=空头减仓。原料在 qcore `valuation_daily.parquet`(市值/估值日频)。目前仍是语料里的框架概念,**尚未接成可计算指标**。

**大单净流入**(主力净流入):
个股大单净流入,被 B 系战法当作**可选加分项**消费(LEFT JOIN,缺失默认 0)。原由 Tushare `moneyflow` 提供;Tushare 退役后**保持缺省不接入** —— akshare 等价源走东财、此环境不可靠,且 5% 阈值单位无法在退役后验证(见 [ADR-0001](docs/adr/0001-retire-tushare-backend.md))。

## Relationships

- **Mode** 决定跑哪些功能;**Source** 决定字节从哪来。两者正交 —— 同一个 JNB Mode 可由 qcore、akshare 或(曾经的)Tushare 供数。
- **JNB Mode** 的功能只消费 **K线** + **市值** + **大单净流入**,三者免费源全部可得。
- **qcore** 与 **akshare** 同一血缘(akshare qfq 日线);qcore 是其缓存/高速形态。

## Example dialogue

> **用户:** 「那 7 个方法的数据,akshare 没有吗?qcore 也没有吗?」
> **开发者:** 「数据**有** —— qcore 湖里现成躺着指数/龙虎榜/财务/市值,akshare 库也能现拉资金流/实时。之前缺的只是我们的**封装类**没把它们接出来,不是源没有。」

## Flagged ambiguities

- 「akshare/qcore 没有那些数据」混淆了 **Source 封装覆盖**(我们的 client 只实现 2 个方法)与 **Source 数据可得性**(湖/库其实持有远更多)。已澄清:数据存在,只是封装薄。
- 「qcore 模式」vs「qcore 数据源」—— `DATA_MODE=qcore` 是个 Mode 取值,但 qcore 本质是 Source。**已定(2026-06-08 grill):不拆独立 Source 轴**,DATA_MODE 保持单一扁平枚举 `jnb|qcore|akshare|websearch`。理由:qcore 与 akshare 同源(缓存 vs 现拉)、Tushare 休眠且无盘中接口 —— 真实数据源只有一族,为「一轴半」的来源拆出 DATA_SOURCE 属于过度抽象。枚举里 qcore/akshare 并列,语义是「同一份数据的本地缓存 vs 现拉」两种取数策略,非两个数据提供商。详见 [ADR-0002](docs/adr/0002-flat-data-mode.md)。
