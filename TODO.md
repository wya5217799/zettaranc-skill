# TODO

> Zettaranc Skill 待办清单
> 更新日期：2026-05-29（活跃市值择时 ⏸️ 搁置）
> 当前版本：v2.4.0
> 状态：✅ 已完成 / ⏳ 进行中 / 📋 待规划

---

## ✅ 已完成（v2.4.0）

### 数据层
- [x] Tushare API 接入（Pro API + 中转 URL）
- [x] 数据源统一前复权（`pro_bar adj='qfq'`）
- [x] SQLite 本地缓存层（8 张表 + 索引）
- [x] 指标缓存表（`indicator_cache`）每日快照
- [x] Tushare 官方指标对比表（`tushare_indicator_cache`）用于 diff 验证
- [x] 数据同步工具（单股票/批量/增量/全量）
- [x] 限流控制（120次/分钟）

### 基础指标（60+）
- [x] MA / EMA / SMA（通达信标准递推）
- [x] KDJ（参数 9,3,3，递推实现）
- [x] MACD（12,26,9，O(n) 递推，与 Tushare  diff 一致）
- [x] RSI（6/12/24，**已修复为递推 SMA**，与 Tushare diff 一致）
- [x] WR 威廉指标
- [x] BBI 多空指标
- [x] 布林带（上/中/下/宽度/位置）
- [x] DMI（+DI, -DI, ADX）
- [x] 量比
- [x] 砖形图（**已修复递推逻辑**，与通达信一致）

### 价格形态
- [x] 双线战法（白线 EMA(EMA(C,10),10) + 黄线 4参数 BBI）
- [x] 单针下 20/30
- [x] 双枪
- [x] 砖形图历史趋势 + 反包检测

### 量价信号
- [x] 防卖飞 V1.4 评分（5 分制自动化）
- [x] 卖出评分（出货信号扫描）
- [x] 北斗/缩量/假阴真阳/放量阴线检测

### 买入战法
- [x] B1 量化（J ≤ -10 + N型结构 + 缩量回调）
- [x] B2 量化（涨幅 ≥ 4% + 放量 + J < 55 + 无上影线）
- [x] B3 量化（B2 后十字星/小阴线 + 平开一致）
- [x] SB1（超级 B1）
- [x] 长安战法（B1 + 放量长阳 + 缩半量）
- [x] 四分之三阴量（真假突破判断）
- [x] 娜娜图形
- [x] 异动地量
- [x] 平行重炮 / 多门重炮
- [x] 坑里起好货
- [x] 对称 VA（时间+空间对称）

### 卖出/逃顶
- [x] S1 逃顶（高位放量阴线）
- [x] S2 逃顶（挑前高 + MACD 顶背离）
- [x] S3 逃顶（反抽巨量下沿）
- [x] 砖形图止损信号（红砖翻绿）

### 选股体系
- [x] 曼城评分体系
- [x] 趋势评分 / 量价评分 / 风险评分
- [x] 完美图形识别
- [x] B1 选股扫描
- [x] 每日五步工作流（CLI）

### 持股诊断
- [x] 当前状态扫描（BBI/白线/黄线位置）
- [x] 防卖飞评分
- [x] 出货信号扫描
- [x] 战法匹配（B1/B2/B3/SB1 可买区间）
- [x] 止损/止盈位提示

### 观察池
- [x] 自选股增删改查
- [x] 批量监控 + 每日信号扫描
- [x] 异动检测

### 回测
- [x] 单策略回测
- [x] 多策略组合回测
- [x] 多股票组合回测
- [x] 资金曲线 / 夏普比率 / 最大回撤

### CLI 工具
- [x] `python -m modules.cli analyze` — 个股分析
- [x] `python -m modules.cli backtest` — 策略回测
- [x] `python -m modules.cli screener` — 选股扫描
- [x] `python -m modules.cli watchlist` — 观察池管理
- [x] `python -m modules.data_sync stk-factor` — Tushare 指标同步

---

## 📋 待实现（量化指标缺口清单）

> 按 **实战价值 × 实现难度** 综合排序

### P0 — 高价值 + 实现简单（建议优先）

- [x] **滴滴战法** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/trading-core.md` 3.11
  - 定义：高位连续两根阴线下台阶，第二根收盘价 < 第一根最低价，量没明显缩
  - 价值：最高优先级卖出信号，绕过防卖飞直接清仓
  - 难度：低（2根K线模式识别）
  - 文件建议：`modules/indicators/exit_signals.py` 或 `modules/strategies.py`

- [x] **MACD 金叉空 / 死叉多** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/indicators.md` 3.12
  - 定义：眼看金叉/死叉即将形成，白线突然拐头，陷阱识别
  - 价值：避开 90% 诱多/诱空陷阱
  - 难度：低（MACD 序列局部极值检测）
  - 文件建议：`modules/indicators/core.py` + `modules/strategies.py`

- [x] **祖冲之法（目标价计算）** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/advanced-patterns.md`
  - 公式：目标价 = 2a - b（a=近期高点, b=近期低点）
  - 价值：判断主力出货位置，模糊的正确
  - 难度：低（纯数学公式）
  - 文件建议：`modules/indicators/price_patterns.py`

### P1 — 高价值 + 实现中等

- [x] **主力出货五式精细识别** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/sell-discipline.md` 3.15
  - 现状：只有 S1 简单大阴线，缺少五种具体形态
  - 五式：
    1. 加速后单日放天量大阴
    2. 次高点巨量长阴
    3. 阶梯放量下跌（一组K线）
    4. 双头双放量巨阴
    5. 顶部绿肥红瘦（阴量>阳量）
  - 价值：真出货 vs 假洗盘的精确判断
  - 难度：中（需要量能序列 + 形态组合识别）
  - 文件建议：`modules/indicators/volume_patterns.py` + `modules/strategies.py`

- [x] **灾后重建（缩量回踩黄线）** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/advanced-patterns.md`
  - 定义：放量金叉后缩量回踩黄线，交易价值最大
  - 价值：震仓后的最佳买点
  - 难度：中（需要检测「回踩黄线」+「缩量」+「前期放量金叉」）
  - 文件建议：`modules/strategies.py`

- [x] **跃跃欲试（横盘放巨量三次）** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/advanced-patterns.md`
  - 定义：横盘期间放巨大量，红长绿短，至少三次后突破概率大
  - 价值：横有多长竖有多高
  - 难度：中（横盘区间检测 + 巨量计数）
  - 文件建议：`modules/strategies.py`

- [x] **关键 K 识别** ✅ v2.4.0+ 已实现
  - 来源：`knowledge/key-candles.md`
  - 定义：六种趋势转换的关键K（下跌→上涨、横盘→上涨、上涨→下跌等）
  - 价值：趋势反转/衰竭的量化标记
  - 难度：中（「关键位置」的量化定义较主观）
  - 文件建议：`modules/indicators/price_patterns.py`

### P2 — 高价值 + 实现较难

- [ ] **活跃市值择时** ⏸️ **搁置待议**
  - 来源：`knowledge/trading-core.md` 3.6 / `knowledge/market-macro.md`
  - 定义：4% 多头才干活，-2.3% 空头就休息
  - 价值：Z 哥说「择时永远第一」，所有战法的前提
  - 难点：指南针专有指标，Tushare 无对应接口
  - 状态：**已搁置**，后续待讨论替代方案（全市场成交额代理 / 指南针数据导入）
  - 文件建议：新增 `modules/market_timing.py`

- [x] **三波理论识别** ✅ v2.6.0 已实现
  - 来源：`knowledge/indicators.md` 三波理论
  - 定义：建仓波（25-50%涨幅，无涨停）→ 拉升波（快速脱离，有涨停）→ 冲刺波（最后主升）
  - 价值：直接决定 B1 能不能做（建仓波可干，拉升波等回调，冲刺波不看）
  - 实现：`modules/indicators/wave_theory.py`
  - 测试：`tests/test_wave_theory.py`（12 个用例全绿）

- [x] **麒麟会四阶段识别** ✅ v2.6.0 已实现
  - 来源：`knowledge/indicators.md` 3.9 / `knowledge/iron-butterfly.md`
  - 定义：吸筹 → 拉升 → 派发 → 回落
  - 价值：判断主力阶段，决定操作策略
  - 实现：`modules/indicators/kirin_detector.py`（评分制 + 子类型判断）
  - 测试：`tests/test_kirin_detector.py`（15 个用例全绿）

### P3 — 中价值 / 概念性

- [ ] **蜈蚣图识别**
  - 来源：`knowledge/trading-core.md` 3.0b
  - 定义：堆量不涨 + 长上下影十字星交替 + 无呼吸节奏
  - 价值：直接排除垃圾票
  - 难点：「呼吸节奏」量化定义较模糊
  - 文件建议：`modules/screener.py`（作为过滤条件）

- [ ] **牛绳理论量化**
  - 来源：`knowledge/trend-lines.md`
  - 定义：白线在黄线上 = 主力牵牛，跌破 = 牛绳断
  - 现状：双线战法已有基础，但「牛绳」概念未单独封装
  - 难度：低（在现有双线基础上加一层抽象）
  - 文件建议：`modules/indicators/price_patterns.py`

- [ ] **量比战法引擎**
  - 来源：`knowledge/trading-core.md` 3.6
  - 定义：集合竞价量比计算 + 攻击日/出货日判定
  - 价值：开盘精细择时
  - 难点：需要分钟级/竞价数据，Tushare 免费版可能不支持
  - 文件建议：新增 `modules/market_timing.py`

- [ ] **沙漏评分 V9**
  - 来源：TANGOO 09 / 复盘专用z 10
  - 定义：S_shape + Delta 评分引擎，通达信已有指标
  - 价值：Z 哥说的「完美图形」量化标准
  - 难点：需要了解通达信沙漏指标的具体算法
  - 文件建议：新增 `modules/sandglass.py`

---

## ⏳ 进行中

- [x] ~~v2.4.0 砖形图/MACD/RSI 递推修复~~ → **已完成**
- [x] ~~v2.4.0 数据源统一前复权~~ → **已完成**
- [x] ~~v2.4.0 Tushare 指标对比表~~ → **已完成**
- [x] ~~v2.5.0 P0+P1 指标批量完成~~ → **已完成**
- [x] ~~v2.6.0 P2 核心模块（三波理论 + 麒麟会）~~ → **已完成**
- [x] ~~v2.6.0 集成工作（strategies / screener / cli / 文档）~~ → **已完成**

---

## 版本路线图

| 版本 | 主题 | 状态 |
|------|------|------|
| **v2.3.x** | indicators 拆分子模块 + 缓存层 | ✅ 已完成 |
| **v2.4.0** | CLI 工具 + 回测框架 + 递推修复 | ✅ 已完成 |
| **v2.5.0** | P0/P1 指标补全（滴滴/金叉空/出货五式/灾后重建） | 📋 规划中 |
| **v2.6.0** | P2 核心模块（活跃市值/三波理论/麒麟会） | 📋 规划中 |
| **v2.7.0** | 沙漏 V9 + 蜈蚣图 + 牛绳理论 | 📋 待定 |
| **v3.0.0** | 少妇模拟器完整版（自动化择时+选股+买入+卖出闭环） | 🎯 长期目标 |
