# 🐳 Whale Watcher — GitHub Issues 完整记录

> 仓库：[yuqiaowu/whale-watcher](https://github.com/yuqiaowu/whale-watcher)  
> 导出时间：2026-03-25 16:02 CST  
> 共 18 条 Issue

## 📋 Issue 总览

| # | 状态 | 标题 | 创建时间 |
|---|------|------|----------|
| #1 | ✅ CLOSED | 检查最近3笔失败订单，提升AI提示词 | 2026-03-01 |
| #2 | 🔵 OPEN | 增强 AI 风控机制：增加 ADX 强制拦截与右侧突破（4H K线）自动确认 | 2026-03-04 |
| #3 | 🔵 OPEN | [Bug/Refactor] 修复巨鲸情绪评估模块：解决哈希覆盖、对数权重失效与 Altcoin 数据污染问题 | 2026-03-04 |
| #4 | 🔵 OPEN | # Issue: 为 AI 交易模型实现动态止盈止损（移动止损与追踪锁利） | 2026-03-04 |
| #5 | 🔵 OPEN | 优化通知模块 (Notifier) 以支持止盈止损调整提醒 | 2026-03-04 |
| #6 | 🔵 OPEN | 修复前端“代币流量 (Token Flow)”归零及情绪分数偏差的 Bug | 2026-03-04 |
| #7 | 🔵 OPEN | 放宽 ADX 趋势过滤条件，启用震荡市全天候交易能力 | 2026-03-04 |
| #8 | 🔵 OPEN | AI交易权限解锁与量化风控(分批止盈)升级 | 2026-03-04 |
| #9 | 🔵 OPEN | AI交易记忆模块(Agent Memory)幻觉修复与盈亏反馈闭环升级 | 2026-03-05 |
| #10 | 🔵 OPEN | [MILESTONE] 交易引擎 v2.0：从“规则驱动”进化为“权重驱动”的自主决策模型 #16 | 2026-03-07 |
| #11 | 🔵 OPEN | [Fix/Feature] 修复 AI 数据失明、防御性崩溃及重构流向逻辑 (AI Data Accuracy & Lo | 2026-03-11 |
| #12 | 🔵 OPEN | [Refactor/AI] 从规则集升级到思辨框架：AI 交易员认知模型重构 (Prompt Engineering O | 2026-03-11 |
| #13 | 🔵 OPEN | 3月18日 系统升级核心 Issue 修复报告 | 2026-03-18 |
| #14 | 🔵 OPEN | 大脑强制进化 (Qlib 模型失效) | 2026-03-19 |
| #15 | 🔵 OPEN | [Dolores 升级 v2.1 总结报告]：Qlib 复活、风控盾 v2 与 仓位管理全自动化 | 2026-03-23 |
| #16 | 🔵 OPEN | Dolores” AI 交易系统加固与逻辑优化 | 2026-03-25 |
| #17 | 🔵 OPEN | AI 计算错误bug优化 | 2026-03-25 |
| #18 | 🔵 OPEN | 🛡️ Issue Fix: AI 自生成低 RRR 开仓信号却未自我拦截 | 2026-03-25 |

---

## 📖 Issue 详情

### ✅ Issue #1: 检查最近3笔失败订单，提升AI提示词

> **状态**: CLOSED  
> **标签**: 无  
> **创建时间**: 2026-03-01  
> **关闭时间**: 2026-03-01  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/1

### 问题背景 / Background
近期监控到 AI 代理连续发生了 3笔触发止损的失败多单（DOGE, SOL, ETH）。团队提取了底层的市场快照数据和 AI 的决策日志（`agent_decision_log`）进行了详细复盘，发现系统的开仓条件与风控模块在极端行情下存在漏洞，同时 AI 的“自我反思记忆”模块未能正确流转。

### 失败订单分析 / Analysis of Failed Trades
1. **DOGE (逆势接飞刀)**: 仅凭极度负资金费率（预判轧空）即在 RSI 高达 40 时买入，未等待深跌出现的极致超卖（<30）或长下影线，最终死于单边下跌趋势。
2. **SOL (突破骗线与窄止损)**: 巨鲸吸筹驱动右侧突破入场，但在高波动环境下设立了仅有 3% 左右的极窄止损，迅速被市场日常噪音（插针）扫损洗盘。
3. **ETH (清算高潮接盘)**: 在市场出现极端的空头爆仓（Liquidation Climax）时买入。错把流动性抽干后的最后一击当作持续动能，买在了局部最高点。
4. **记忆重置 Bug**: AI 在底层数据库生成了极高质量的反思文字（例如明确知道自己“过早逆势”、“没等右侧确认”），但由于本地 JSON 同步断层，导致这些反思未能成功注入到下一轮的系统 Prompt 中，AI 陷入了“天天失忆重犯错”的循环。

### 已提交的修复与优化 / Resolutions (PR/Commit)
针对上述问题，已对核心决策层 [ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0) 的 System Prompt 进行了硬性强化约束，并修复了本地记忆流：

- [x] **建立反向流动性陷阱规则 (Reverse Liquidation Trap)**
  明确禁止在发生巨大的单边爆仓后去顺势追单（例如巨大空头爆仓后禁止追多）。防止接盘清算高潮。
- [x] **强化极端逆势开仓条件 (Symmetrical Pain Trade Logic)**
  多空双向增加防骗线机制：对于博弈极度资金费率或爆仓的反转，**强制要求 RSI 严格 <30 或者 >70**，或者出现 4H 级别重大的反转实体影线，杜绝半山腰拦车。
- [x] **引入波动率弹性止损 (NATR Stop-Loss Enforcement)**
  取消固定的静态止损百分比经验值。要求 AI **强制以不低于 1.5倍真实波动率 (NATR)** 的距离设置止损空间。若风控超标（如大于2% NAV），强制要求其缩小头寸(Position Size)或者放弃开仓。
- [x] **修复 AI 反思记忆模块 (Memory Stream Fix)**
  修正了从 DB 抽取最近 5 笔交易及其反思（Context & Reflection）同步回 [frontend/data/agent_memory.json](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/frontend/data/agent_memory.json:0:0-0:0) 的逻辑，确保 AI 每次开仓前能充分“阅读”自己最近的血泪教训。

---

### 🔵 Issue #2: 增强 AI 风控机制：增加 ADX 强制拦截与右侧突破（4H K线）自动确认

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/2

解决方案 (Proposed Solution) ：

需要在 ai_trader.py的风控核心函数 validate_and_enforce_decision中引入物理级别的拦截层：

AI 意图解析 (Intent Parsing)：

提取 entry_reason 字段（兼容字典与字符串格式防崩溃），检测是否包含突破特征词（如 "突破", "右侧", "wait", "breakout" 等），标记为 is_breakout_trade。
带特赦的 ADX 拦截 (Strict ADX Filter)：

提取市场实时 adx_14。
如果 ADX < 20，正常情况下将订单操作强行修改为 "REJECTED"，杜绝无趋势行情盲目开单。
例外（特赦）：如果该单被标记为 is_breakout_trade，则豁免 ADX 拦截，交由突破验证器处理。
4H 级别右侧突破验证 (Right-Side Breakout Verification)：

如果是突破交易，后端通过 API 拉取交易所的实时 4H K线。
对比最后一根已收盘的 4H K线（last_closed_candle）与它之前的 5 根 K线做极值判定（Prev High / Prev Low）。
如果做多但收盘价未突破前高，或做空但未跌破前低，则物理拦截该单，修改状态为 "WAIT"，系统处于哨兵监控模式，直到真正的右侧收盘突破才放行吃单。

影响 (Impact) ：

提升了交易系统的容错率，减少在震荡行情或假突破时的不必要亏损，让 AI 的交易行为完全契合其设定的策略思路。

---

### 🔵 Issue #3: [Bug/Refactor] 修复巨鲸情绪评估模块：解决哈希覆盖、对数权重失效与 Altcoin 数据污染问题

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/3

背景 (Background) 

crypto_brain.py中的 analyze_transfers_v1（情绪打分内核）和 merge_and_filter_txs（去重器）存在三处会导致 AI 对市场判断产生严重误导的隐蔽型逻辑 Bug。主要体现在：多币种连环 Swap 被覆盖、超级巨鲸的资金话语权被异常压缩、以及 MEME 币波动污染了主网币（ETH/SOL）的情绪分析池。

问题症状 (Symptoms & Real Case)

Swap 动作自我覆盖：巨鲸在链上使用 SOL 兑换为 USDC，这会抓取到两条记录（SOL 卖出与 USDC 获取），但这原本是一笔 tx_hash。在先前的字典过滤 merged_map[tx['hash']] 中，后者直接覆盖了前者，导致 真正的深度抛压/买入记录被完全掩饰。
权重失真 (Log10 Issue)：情绪系统先前的计分体系采用 math.log10(amount_usd)，这导致 1,000 万美金砸盘的严重程度仅仅是 1 万美金散户买单权重的不到两倍。真实超级巨鲸的影响被蚂蚁海量交易稀释抹平。
情绪杂交污染：AI 获取全局转账（含 SHIB, PEPE, WIF 等热钱转移）后，计算 ETH 或 SOL 时未排除这些非标资产（Altcoins）。导致 AI 因为 Meme 币种的情绪异动，错判主标的（ETH/SOL）的大势。
修复方案 (Resolutions)

升维去重字典键名：
将 merge_and_filter_txs的去重防撞键修改为双重元组：(tx['hash'], tx['symbol'])支持单笔哈希中多币种换手的独立存活分析。重构计算标量：
将指数抹平工具 math.log10 替换为了 平方根 (math.sqrt)。例如 $10k 获得 100 占比，$10M 获得 3162 占比。放大超级巨鲸在加权平均算法时的绝对统治力。

构建同源资产隔离墙：
为函数级分析器 analyze_transfers_v1(transfers, market_metrics, target_symbol="UNKNOWN")新增目标锁定传参。
在遍历中拦截计算：if symbol not in STABLECOINS and symbol != target_symbol: continue。严格保证 AI 在推演 ETH 时，只感知 [ETH + 全局稳定币] 的净流向，根除垃圾数据的交叉干扰。

影响 (Impact) 

修复后，系统重获“抓大放小”的敏锐度。V2 分析引擎提供给 AI 的 sentiment_score（情绪分）与 confidence_score（信心分数）将完全贴合实战中主流币对资金大额吞吐的真实反馈。

---

### 🔵 Issue #4: # Issue: 为 AI 交易模型实现动态止盈止损（移动止损与追踪锁利）

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/4

## 📝 问题描述
当前的 AI 交易模型 ([ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0)) 仅在开仓的瞬间设置一次固定的止损 (SL) 和止盈 (TP)。一旦订单生效，AI 就失去了“修改”这些价位的能力与权限（比如无法在浮盈时把止损位上调来保护本金，也无法在趋势大好时上调止盈让利润奔跑）。为了优化胜率和拉高盈亏比，系统的两端（AI 大脑提示词 和 OKX 订单执行器）都需要进行大重构，使其支持对存量合约订单的动态算法调仓。

## ✨ 实现目标
- [x] **赋予 AI “持仓感知”能力:** 修改 [ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0) 的系统提示词 `SYSTEM_PROMPT`，强制 AI 在开仓前“检查所有存量订单的浮盈 (`pnlPercent`)”。当浮盈突破 5% 时，AI **必须**下发追踪止损的指令。
- [x] **新增调仓动作指令 (Agent):** 给 AI 动作库添加 `adjust_sl` 指令模块。允许 AI 生成更新存量订单方案 `exit_plan`（包含修改后的 `stop_loss` 和/或 `take_profit`）的标准动作输出。
- [x] **绕过风控层拦截:** 在风控函数 [validate_and_enforce_decision](cci:1://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:663:0-863:19) 中加入特批通道，允许 `adjust_sl` 等保本动作丝滑通过，并且不占用开仓数量的安全阈值。
- [x] **执行层对接 (Executor):** 在 [okx_executor.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/okx_executor.py:0:0-0:0) ([execute_trade](cci:1://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/okx_executor.py:237:4-542:19)) 接住模型下发下来的 `adjust_sl` 格式指令。
- [x] **沙盒/模拟模式 (Shadow Mode) 数据流对接:** 让本地存量的模拟盘 JSON（[portfolio_state.json](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/ai-crypto-agent/portfolio_state.json:0:0-0:0)）能正确处理 `adjust_sl` 逻辑并刷新账本中的预估止盈止损点位。
- [x] **实盘 OKX API 对接:**  重构了完整的双重挂单更新逻辑：自动获取已有未触发挂单 -> POST `/api/v5/trade/cancel-algos` 一键撤销过时算法单 -> 遍历双向真实仓位推导演算买卖方向 -> POST `/api/v5/trade/order-algo` 重新上膛全新的 OCO 双向止盈止损单。

## 🛠 修复细节展示
1. **Prompt 调教 ([ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0)):** 添加了强制性纪律指令：`If floating profit is > 5%, you MUST output an adjust_sl action... Update stop_loss and/or take_profit parameters in exit_plan`。
2. **底层黑名单豁免 ([ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0)):** 修复了原 `is_trade` 常量只认 [open_](cci:1://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/okx_executor.py:544:4-551:16) 和 `close` 的隐性报错流，目前完美抓取拦截了 `adjust_sl` 并调用 `executor.execute_trade`。
3. **安全而严谨的执行引擎 ([okx_executor.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/okx_executor.py:0:0-0:0)):** 包含以下实战防呆逻辑:
   - 动态获取属于该品种的全部算法委托。
   - 对废弃或不在水里的止损限价单予以清除。
   - **循环查询仓位方向（双重保险）：** 不死板地拿数组第1个元素（防止全仓/双向开单错乱），灵活提取当前 `posSide`（多或空）来逆向决定接盘网是不是 `buy` 还是 `sell`。
   - 组装成 OCO 条件单交回 OKX 完成利润护盾。

---

### 🔵 Issue #5: 优化通知模块 (Notifier) 以支持止盈止损调整提醒

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/5

## 📝 问题描述
在 `ai_trader.py` 中加入了动态跟踪止盈止损 (`adjust_sl`) 功能后，原有的通知模块 (`notifier.py`) 由于不认识这个新动作类型，会默认落入“非做多(long/buy)”条件分支的 else 判断中，导致当机器人拉高止损保护时，Telegram 和 Discord 给用户发送的是一个警告性的红色圆点 `🔴` 或红色边框，同时标题显示为默认的 `TRADE EXECUTED`。这会让用户产生“仓位被无端平定或做空”的恐慌和误解。

## ✨ 实现目标
- [x] **状态识别拦截:** 在 `notifier.py` 内追加对 `action == "adjust_sl"` 状态的精准捕获。
- [x] **重构通知视觉 UI (Telegram/Discord):** 针对调整止损止盈操作设定专有的图标、颜色代码以及业务相关的通知文案。

## 🛠 修复细节展示
更改了 `backend/notifier.py` 的通知下发逻辑架构：
1. **专属图标与文案:** 捕获到 `"adjust_sl"` 动作时，标题状态文字变为 **`🛡️ RISK ADJUSTED`**。有别于开单的绿灯 🟢 和平单的红灯 🔴，为这笔锁利挂单赋予了坚实的安全感。
2. **Discord 侧边带涂装:** 在发送向 Discord 配置的 `Color Code` 中，把做多的 🟩(绿色) 和 做空的 🟥(红色) 之外开辟了第三类专供通知—— **🟦 深蓝色 (`3447003`)**。
3. 这些修改结合之前打通的大脑和执行器逻辑，现在当账户浮盈超过 5%，不再会收到一个刺眼的红灯，而是会看到蓝色盾牌通知利润已经被锁住了。

---

### 🔵 Issue #6: 修复前端“代币流量 (Token Flow)”归零及情绪分数偏差的 Bug

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/6

## 📝 问题描述 (Bug Report)
监控面板前端经常出现“代币流量（Token Flow）”长期为 `0` 的异常情况。
经排查底层数据处理模块 (`backend/crypto_brain.py`)，发现在 `analyze_transfers_v1` 函数中存在一段过度严格的隔离过滤代码：
```python
if symbol not in STABLECOINS and symbol != target_symbol:
    continue
```
由于该逻辑，任何非稳定币（USDT/USDC）且非目标原生代币（如 ETH 或 SOL）的巨鲸转账事件（例如系统原本应该监听的 SHIB、PEPE、LINK、WETH 等重要风向标代币的千万级别大单抛售或吸筹）会被系统直接丢弃。
这不仅导致了面板上以太坊等链的代币总流量统计残缺，更导致 AI 进行全局**情绪评分 (Sentiment Score)** 和**操作信心分 (Confidence Score)** 的计算时“以偏概全”，失去了对周边山寨市场大资金动向的感知。

## ✨ 修复目标 (Resolution)
- [x] **移除过度过滤:** 删除由 `crypto_brain.py` 错误引入的 `target_symbol` 隔离墙，让系统重新放行所有配置文件 `TOKENS` 白名单内的链上大额转账事件。
- [x] **恢复流量统计:** 确保巨鲸对重要山寨币/Meme 币的操作金额能重新被正确累加至 `token_net_flow` 和 `token` 累加器中。
- [x] **数据反馈闭环:** 经过平方根（`math.sqrt`）权重的计算，这部分流失的庞大金额将被修正回 AI 每天的 `w_score` 总分池子中，使其预判大盘变盘的指标更加敏感。

## 🛠 修改明细 (Changelog)
**文件**: `backend/crypto_brain.py` -> `analyze_transfers_v1` 方法。
- **删除了以下代码行**：
  ```python
  if symbol not in STABLECOINS and symbol != target_symbol:
      continue
  ```
- **保留了基础业务流**：代币属性分离判定依然完整（稳定币进入 `stable`，其他所有非稳定币通证准确流入 `token` 作为行情燃料参考）。

## 🧪 验证结果 (Verification)
- 后端脚本重新拉取区块解析时，不会再将非 ETH 的链上白名单资产丢弃。
- 经过下一轮定时同步 (`trigger_sync.py` 或由系统 Cronjob 触发的大脑刷新)，前端 Web 面板的“代币流量”图表将长出真实的直方图数据。AI 得分引擎重回完全体。

---

### 🔵 Issue #7: 放宽 ADX 趋势过滤条件，启用震荡市全天候交易能力

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/7

## 📝 问题描述
在过去的系统防守策略中，为了防止由于市场**无趋势震荡（ADX < 20）**带来的假突破与来回插针插爆静态止损点，我们在 [ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0) 的执行校验层以及提示词中，加入了名为 `ADX No-Trade Zone` 的硬性阻断规则。
这套“宁可踏空绝不挨刀”的古老防区，虽然在单边市保护了胜率，但在近期造成了**系统过早地下轿，甚至因为底层严格的拦截而错过了至少两波巨轮级别的前置吸筹右侧启动行情（处于启动前夕时，指标的 ADX 往往都还没越过 20 的门槛）**。

随着近期我们完成了【追踪止损保本与动态上移止盈】的高级战术系统 (`adjust_sl`)，机器人在弱势震荡环境中的近战护具已经全面升级，这使得 ADX < 20 时的“盈亏护城河脆弱”短板被彻底抵消。原有的刚性策略显得过于死板。

## ✨ 实现目标
- [x] **解放系统指令:** 更新系统大脑（[ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0) 的 `SYSTEM_PROMPT`），将 ADX < 20 的禁止状态改为“允许进入但须保持谨慎”的 `ADX Choppy Zone` 状态。
- [x] **战术策略配套:** 让 AI 知晓在此时可以进场，但命令其在此环境下一旦产生利润，必须**极其频繁而敏锐地利用我们刚写的动态调整命令（Dynamic SL/TP）来贴身保护订单或锁利**。
- [x] **撤除底层阻断器:** 在底层执行引擎过滤链条中，删去 `action == "REJECTED"` 的一刀切逻辑，使其转化为仅仅是记录风险日志（`⚠️ ADX Warning`），而不会再去物理截断原本极具潜力的鲸鱼跟随开单。

## 🛠 修改明细
**文件**: [backend/ai_trader.py](cci:7://file:///Users/yuqiaowu/Desktop/%E7%AC%AC%E4%B8%80%E4%B8%AA%E9%93%BE%E4%B8%8A%E9%A1%B9%E7%9B%AE/%E9%B2%B8%E9%B1%BC%E7%9B%91%E6%8E%A7/backend/ai_trader.py:0:0-0:0)
1. 将 Prompt `4. ADX No-Trade Zone (HARD RULE — NEVER VIOLATE)` 模块改写为了 `4. ADX Choppy Zone (Proceed with Caution)`。
2. 明确指示该阶段开仓时的配套要求：“You ARE ALLOWED to open directional bets here, but you MUST rely heavily on your dynamic Stop-Loss and Take-Profit adjustments to survive the noise.”
3. 移除了底部执行验证代码 `valid_and_enforce_decision` 中当 `adx_val < 20` 时的拒绝接单行为，代之以警告放行通过。

## 🧪 建议的验收测试
- 观察当整体大盘进入横盘/回调低谷位开始反弹、且 ADX 仍然小于 20 的关键前夜时，机器人是否开始正常执行鲸鱼跟单（过去此处将被死死拦截）。
- 查看日志打印，确认遇到低 ADX 时控制台会打出提示 `⚠️ ADX Warning: ... Relying on Dynamic SL/TP` 而不是直接踢除这笔委托单。

---

### 🔵 Issue #8: AI交易权限解锁与量化风控(分批止盈)升级

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-04  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/8

## 📌 背景与动机
之前的 AI 交易系统在执行效率和风控管理上存在两个致命的限制：

1. **“右侧突破”陷阱（过度限制的入场）：**
   AI 经常能根据鲸鱼吸筹、极度负的资金费率和爆仓数据，精准识别出完美的左侧反转向下或向上的入场点。但是，旧系统中有一段硬编码的 Python 校验逻辑，强制要求“4小时K线收盘价必须在数学上突破前5根K线的最高/最低点”。由于大语言模型（LLM）缺乏“视觉图表逻辑”，并且不擅长进行精确的小数对比，它经常会在感觉应该入场时提前宣告“突破”。结果，物理代码无情地拦截了它的操作并强制将状态改为 `WAIT`，导致 AI 错失了本来已经正确识别的绝佳入场时机。

2. **“过山车”困境（要么全买要么全卖）：**
   一旦进入盈利的持仓，AI 的动作菜单只允许它执行 `hold`（持有）、`adjust_sl`（追踪止损）或 `close_position`（全仓平盘）。这种二元对立的策略意味着 AI **无法进行部分平仓**（比如在遇到阻力位时卖掉一部分锁定利润，让剩下的部分继续奔跑）。此外，`adjust_sl`（调整止损）这个命名误导了 AI，导致它忘记了其实它还可以向上调整止盈（`take_profit`）。这使得原本高达 10% 的账面浮盈，一旦遇到剧烈插针，很容易变成保本甚至小亏。

## 🛠 部署的升级方案

### 1. 终极放权（拆除物理拦截网）
- **Prompt 大修 (`ai_trader.py`)：** 彻底抹除了所有关于“等待右侧突破确认”或者“左侧信号右侧入场”的强制规定。AI 现在获得了 100% 的战术开火权，只要各种数据（指标、鲸鱼动向、清算）形成共振，它就可以直接下达 `OPEN_LONG` 或 `OPEN_SHORT` 指令。
- **底层校验拆除 (`ai_trader.py`)：** 删除了底层那 40 行的 `Verify Right-Side Breakout` 拦截代码，它再也不会截胡 AI 的下单意图了。

### 2. 分批止盈（锁定收益防抖护城河）
- **菜单豪华扩充 (`ai_trader.py`)：** 为已有持仓的操作菜单引入了三种精细化指令：
  - `reduce_25`: 当探测到“潜在风险”或上涨动能衰竭时，平掉 25% 锁定利润。
  - `reduce_50`: 当价格撞倒重大阻力/支撑位，但宏观趋势并未彻底走坏时，平掉 50% 落袋为安。
  - `reduce_75`: 当趋势出现极度衰竭但还没完全被破坏时，平掉 75% 极度防守。
- **执行器引擎升级 (`okx_executor.py`)：** 重写了向 OKX 交易所发单和影子数据库的更新逻辑。现在，底层执行器收到 `reduce_` 的指令后，会智能算出当前持仓的确切张数（比如 102 张），精准卖掉对应的比例，并同比例调整剩余仓位的保证金，完美记录部分平仓的收益率。

### 3. 正名与引导（追踪利润最大化）
- **指令更名 (`ai_trader.py`, `okx_executor.py`)：** 将全网代码中的 `adjust_sl` 升级更名为 **`adjust_sl_tp`**。
- **强制指引注入：** 在提示词中非常明确地告知 AI：“Update `stop_loss` AND/OR `take_profit` parameters to trail profits or adapt to new resistance/support.”（追踪利润，并向上调整止损/止盈）。这赋予了 AI 主动出击保护利润的清晰指令，告别被动挨打。

## 🎯 预期成效
- **入场更果断：** 取消了死板的破位限制后，面对轧空和鲸鱼疯狂吸筹，AI 可以第一时间介入。
- **资金曲线更平滑：** 引入 `reduce_50` 一类的操作，意味着系统再也不会坐等所有利润被震荡市洗劫一空，锁利操作将变得非常频繁。
- **消灭精神分裂日志：** 执行层和思考层现在实现了100% 同步，再也不会出现“分析说等着突破，日志却跑去开仓”的尴尬名场面了。

---

### 🔵 Issue #9: AI交易记忆模块(Agent Memory)幻觉修复与盈亏反馈闭环升级

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-05  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/9

## 📌 背景与发现的问题
在近期的实盘运行监控中，我们发现 AI 大模型（`ai_trader.py`）在分析持仓（Portfolio）状态和输出反思日志（Reflection）时，出现了严重的**逻辑幻觉（Hallucinations）**：

1. **“幽灵吃单”幻觉现象：**
   - **症状：** 资金真实报表 `PORTFOLIO_STATE_JSON` 中清楚显示系统当前仅持有 BNB，但在 AI 的自我反思输出里，却凭空捏造出一句：“SOL已经有两个持仓，优先管理现有头寸”，从而导致它错误地停止了正确方向上的加仓动作。
   - **根本原因：** 旧版记忆模块 `TradeMemory.get_recent_performance()` 存在逻辑硬编码缺陷。在注入过去的 5 笔交易快照时，代码简单粗暴地判定：“只要过去的交易指令中不带 `close` 关键字，就一律在这个历史动作后贴上 `🟡 OPEN (still holding)` 的状态标签”。这导致 AI 翻阅自己的交易日记时，看到之前建仓的 SOL 被打着“持有中”的钢印，进而与真实的报表数据产生剧烈的精神分裂。

2. **断层的强化学习（缺乏盈亏感知）：**
   - **症状：** 当喂给大模型过去历史交易时，它只能看到自己当初进场时的指标（如 RSI, ADX）和借口（如看到资金费率为负），但却**不知道这笔交易最终是止盈赚了钱，还是爆仓亏了钱**。这导致它无法通过亏损吸取教训，容易在同样的极端环境下一错再错。
   - **快照维度单一：** 之前的底层快照数据仅仅记录了 RSI、ADX 和 WhaleFlow 等三个维度，丢失了包含布林带（Bollinger Bands）、真实建仓资金费率（Funding Rate）等重要的波动参考指标。

## 🛠 修复与升级方案

### 1. 终结“持仓幻觉”（净化记忆上下文）
- **剥离主观推断标签：** 紧急删除了 `get_recent_performance` 函数中主观臆断的 `(still holding)` 代码块。
- **职责剥离：** 现在记忆模块仅负责作为一个**“无感情的交易动作备忘录”**（记录何时、基于什么技术面发出了什么指令）。判定当前真实拥有哪些头寸的权力，彻底 100% 交还给从交易所（或影子数据库）提取的绝对真理级 `PORTFOLIO_STATE_JSON` 对象。大模型将只以后者作为加权最重的风控基础依据。

### 2. 注入真实盈亏（强化学习闭环成型）
- **引入真实结果对接（Result Context Injection）：** 改写了记忆注入模块逻辑。现在的流程在组装过去的记忆供 AI 反思时，会**自动联动读取真实对账单 `trade_history.json`**（扫描最近的 30 笔流水）。
- **盈亏锚定：** 一旦它发现刚才日记里的建仓行为在不久后有一笔对应的平仓或减仓流水，系统将自动把该平仓的真实盈亏金额（PnL Amount）及盈亏百分比提取出来，并赫然印在当初的决策反思上下文下，如：
  > `Result Context: ✅ 赢利: $85.6 (3.25%) shortly after this.`
  这彻底填补了 AI "只管开枪不管战果" 的缺陷，让大模型自此具备了极其强大的“被打了才知道痛”、“吃过亏下次不要碰”的真实自我迭代反思能力。

### 3. 数据快照降维打击（扩充心智数据锚）
- 更新了 `log_trade` 函数里的 `context` 组装器。
- 新增字段注入：将底层的动态指标体系完整上翻给了 AI，包括了当时下注瞬间的 **`Funding`（资金费率）**，以及 **`BB`（布林带当时所处的宽度和趋势敞口表现）**。通过极大增加大模型的决策训练参数，使得后续哪怕 AI 在布林带极限缩口时因为贪恋负资金费率而遭受假突破亏损，它也能通过这段丰富的带标签记忆日记迅速排雷。

## 🎯 预期成效
- **消除逻辑宕机：** 杜绝了 AI 因为读不懂自己的过期日记而自我阻断开仓机会的乌龙事件。
- **触发高净值交易员式自省：** 带有 PnL 盈亏标注的历史复盘文本强行投喂后，大模型必然会在每一轮输出的 Reflection 里针对自己失败的预测展开深刻批判，实盘防守胜率将产生肉眼可见的质变飞跃。

---

### 🔵 Issue #10: [MILESTONE] 交易引擎 v2.0：从“规则驱动”进化为“权重驱动”的自主决策模型 #16

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-07  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/10

🚀 升级背景
在实盘运行中，我们发现硬编码的交易限制（如“熊市禁止做多”）虽然能规避部分风险，但也由于“教条主义”导致 AI 错失了主流币（如 BTC/BNB/DOGE）的大级别反弹。为了让系统具备顶级交易员的灵活性，我们对决策引擎进行了深度重构：废除硬性禁令，引入动态环境权重矩阵。

🛠️ 核心核心变更
1. 引入“Dolores 全能战术武器库” (5 大 Hypotheses)
AI 现在必须在生成的每一笔决策中，从这 5 种深度逻辑剧本中进行“情境匹配”：

TREND_FOLLOWING：顺应 Qlib 深度学习排名与动量的趋势捕捉。
MEAN_REVERSION：在极端 RSI 乖离与清算潮末端的反向博弈。
MICROSTRUCTURE_SQUEEZE：基于资金费陷阱与 L/S 爆仓燃料枯竭的失衡收割。
NARRATIVE_DIVERGENCE：处理“利好不涨/利空不跌”这种新闻与价格背离的进阶战术。
WHALE_FRONT_RUN：当巨鲸足迹与散户情绪产生史诗级冲突时，赋予“跟随聪明钱”的最高权限。
2. “环境动态权重矩阵” (The Weight Matrix)
废除原有的“禁止令”，改为在不同 regime 下对数据进行非线性权重分配：

BEAR Regime (熊市权重)：
Weight 1 (最高)：阻力位与枯竭度（SMA50/200 结合正费率陷阱）。
Weight 2：巨鲸分配信号（确认反弹的真伪）。
Weight 3：成交量 Z-Score（爆发增长是多头入场的通行证）。
BULL Regime (牛市权重)：
Weight 1 (最高)：支撑位与动量回撤（SMA50/EMA20 支撑）。
Weight 2：Qlib 强弱排名（优中选优）。
Weight 3：清算潮监测（空头燃料是否充足）。
3. 赋予 AI “完全决策自主权” (Full Autonomy)
取消硬性枷锁：AI 允许在任何环境下开多或开多，只要其逻辑分析符合当前的权重分级。
杠杆自由化：取消对熊市多单的硬性 2x 限制，由 AI 根据信心指数（Confidence Score）自行决定仓位与杠杆。
强制反向自检：保留并强化 contrary_signal_check，强制 AI 必须识别并解释“当前最不利的一个数据点”，以对抗确认偏误。
📊 典型逻辑演进 ( Case Study: BNB L/S = 160 )
在捕捉到极其极端的 $L/S = 160.33$ 信号时，系统已对齐最新逻辑：

识别信号：虽然散户多头在踩踏（燃料形成），但极值本身意味着物理极限已到（Exhaustion）。
决策偏移：AI 会将此视为“空头动力即将枯竭”的信号。在此权重下，AI 会优先寻找“剧本 2 (均值回归)”或“剧本 3 (微观结构收割)”，寻找止跌转折点，而非盲目在末端追空。
📈 后续监控重点
 观察 AI 是否能在 Bear Regime 下，通过 Volume Z-Score > 1.0 的特权豁免，成功捕捉到主流币的“隐形鲸鱼”反弹。
 验证 hypothesis_scenario 在实际下单中的分布情况，评估 AI 是否过度倾向于某一种剧本。
 监控 contrary_signal_check 的质量，确保 AI 没有为了下单而应付式地填写冲突分析。

---

### 🔵 Issue #11: [Fix/Feature] 修复 AI 数据失明、防御性崩溃及重构流向逻辑 (AI Data Accuracy & Logic Overhaul)" labels: bug, enhancement, ai-logic, data-pipeline

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-11  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/11

📝 问题背景 (Context)
在此前的线上运行中，AI 在解析市场实况时表现出**“选择性失明”和“逻辑矛盾”**（例如：将代币流入交易所判断为利空，但自身持仓为空头时，却错误地认为二者产生了矛盾）。 经过深度诊断，发现整个监控引擎到 AI 分析层之间，存在隐性的数据截断、NoneType 崩溃炸弹、默认零值污染（Default 0 Pollution）以及提示词对资金流向定义的表述缺陷。

本次合并彻底打通了从 
crypto_brain.py到 ai_trader.py的数据断层，赋予了引擎抗压容错能力，并重塑了 AI 对链上微观结构（资金博弈）的认知体系。

🐛 核心 Bug 修复 (Bug Fixes)
修复 NameError: full_ctx 致命断流
问题：在 ai_trader.py拼接并整合 Whale Context 与 Daily Context 的最后一步，因作用域或连缀错误导致变量崩溃，AI 最终只能收到报错字符串，导致其宣称“由于缺乏数据，被迫保持中立”。
修复：重整上下文拼接顺序，确保全系宏观、日内、链上数据完整流入大语言模型。
根除底层 NoneType 与 UnboundLocalError 崩溃炸弹
问题：针对没有链上或爆仓数据的资产（如 BTC、BNB、DOGE），当其返回 None 时，Supervisor（风控层在验证 token_net_flow > 0 等条件）以及部分字符串格式化阶段，会直接引发 Python 引擎级崩溃抛错，导致该轮调度卡死。
修复：
在 Supervisor 中添加了严格的 None 兜底和强类型处理。
修复 ls_ratio 变量在仅判断 Long 时初始化，但在判断 Short 时被调用的未定义越界错误。
消除“假性平静”（Default 0 Pollution）
问题：过去在获取不到 OKX 的大户清算数据或流向时，代码图省事硬编码了 .get("key", 0)。这会严重误导 AI，让其以为市场“绝对死寂”，进而得出错误的低波动结论；且该假数据被存入历史库，污染了图表。
修复：全面改写为 None 或显式的 N/A，并在提示层明确告知 AI：“N/A就是没有数据需要忽略，不是0”，以此倒逼 AI 去关注其他有效的替代性指标（如 交易所买卖星级 和 技术面形态）。
✨ 隐患发掘与高阶数据解锁 (Exposed Data Points)
解锁被“截胡”的深层动能指标问题：
market_data.py和后端一直有计算高成本的 MACD 柱状图能量 与 24小时 OI (未平仓合约) 异动率，但在传给 AI 的最后关口被意外遗漏了。
修复：更新 AI 视野面板，在 [技术指标详情] 之中新增组合标签 [RSI/ADX/MACD] 与 [成交量与持仓(OI)]。AI 现在可以执行三维立体动量分析（确认趋势突破是真金白银还是空头平仓）。
修复量化排名显示格式谬误将原版存在误导性的 [量化排名] XX%（容易和波动百分比搞混），硬性纠正为表达精准的 [量化排名] XX.X/100。
🧠 AI 认知与提示词重构 (AI Logic & Prompt Enhancement)
根治“资金流向推演矛盾”
问题：AI 默认有看多偏置，看到流入（INFLOW/+）字眼便盲目映射为利多，导致其在持有空头的情况下，面对代币大举流入砸盘时，爆出逻辑相悖的点评。
修复：对系统的 SYSTEM_PROMPT 下达了强制规约，用近乎严厉的警告重新对齐了正负号概念：
代币流入（加密资产）= 砸盘预期 = 绝对看跌（Bearish）
代币流出（暗中囤积）= 盘面减少 = 绝对看涨（Bullish）
赋予 AI 宏观交易员的“第二层思维”（Edge Cases）
新增高阶特例指令：避免 AI 在极端行情下当刻舟求剑的死脑筋。
特例 A (暗度陈仓)：底部震荡 + 代币无脑转入 + 极端负费率 = 抵押现货作为保证金准备死扛开多（变相看涨）。
特例 B (链上虹吸)：大牛市背景下 + 稳定币小幅流出 = 并非恐慌撤资，可能只是去 DeFi 赚取高额无风险利息（Yield Farming）。
检验核对 (Checklist)
 代码已做格式化以及容错 (f()函数改进等)
 所有无链上接口的标的（BTC/DOGE 等）经过安全放行，不再引发空指针
 Log 打印恢复正常，无崩溃堆栈
 确信 AI 后续对于资金流向的判断具备正确的三观
部署状态 (Deployment Status): 已整合全部代码并通过 Push 部署至 
main(cf5eb670, e09c977e, 6ff6d93f)。等待下一次 Cronjob 运行观测线上实效。

---

### 🔵 Issue #12: [Refactor/AI] 从规则集升级到思辨框架：AI 交易员认知模型重构 (Prompt Engineering Overhaul)

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-11  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/12

📝 改进背景 (Context)
在早期的 V1.0 版本中，我们对 AI (Dolores) 的提示词 (SYSTEM_PROMPT) 采用了大量“填鸭式”的规则教条（例如硬性规定“L/S比>2.0即极度拥挤”、“新闻超12小时即为Price In”）。 我们在回溯交易日志时发现，这种“死记硬背”的规则严重压制了大语言模型（LLM）的推理能力，使它像一个死板的脚本，面对极端行情或复杂背离时往往不知所措或给出自相矛盾的分析。

本次重构删除了大量教条指令，转而植入**“多空博弈框架（The Pain Trade）”与“多路剧本辩论逻辑（Scenario Debate）”**，正式将 AI 从“执行者”升级为具备独立思考能力的“华尔街分析师”。
改进后，AI 的决策的成功率有了明显提升：

<img width="556" height="742" alt="Image" src="https://github.com/user-attachments/assets/dbcb2571-29fd-4699-afc7-271ce2e66a6c" />

🛠️ 核心架构优化 (Prompt Architecture Enhancements)
1. 废除硬编码阈值，激活思维链 (Chain-of-Thought)
What we removed: 移除了针对指标（如多空比、情绪分）绝对数值大小的直接定性指令。
What we added: 改为探针式提问：“观察多空持仓比：哪一方最为拥挤？”，“审视24小时爆仓量：此时谁的痛苦最高？”。
Why it matters: 激活了 LLM 的深层推理网络（CoT）。AI 不再是死板核对阈值，而是能够根据不同币种的波动基数，自主得出当前盘面的相对极值，从而做出更贴合当下行情的动态判断。
2. 移除确认偏差，强迫“多剧本验证” (Forced Scenario Debate)
What we removed: 消除了 Prompt 中对“狙击巨鲸（Whale Front-Run）”或“轧空陷阱（Squeeze）”等激进策略的隐性推崇及偏好权重。
What we added: 引入 GENERATE 3 SCENARIOS — Then Pick the Best 工作流。要求 AI 必须先脑暴 3 种完全不同的剧本，并且必须在结果中明确写出“为什么拒绝了另外两种剧本”。
Why it matters: 极大地降低了 AI 的“拍脑袋开仓”和过度拟合。通过强制它的“自我逻辑交叉辩论”，筛除了绝大多数高风险的冲动交易。
3. 解除新闻八股文，植入“叙事背离”概念 (Narrative Divergence)
What we removed: 删除了简单粗暴的新闻情感极性判定（好消息买，坏消息卖）。
What we added: 设立 NARRATIVE VS REALITY CHECK 关卡。教会 AI 捕捉 Alpha 的核心法则：“好消息满天飞但价格下跌 = 隐蔽出货陷阱；坏消息不断但价格坚挺（不跌反涨）= 暗中吸筹的背离（Divergence）”。
Why it matters: 提升了 AI 识别“利好落地是利空”这种机构操盘手法的能力，完美切入基本面与盘面资金的错配点进行套利。
4. 进化至“痛苦交易论”框架 (The Pain Trade Framework)
What we added: 从传统的“找开仓信号”跃升为“找市场燃料（寻找尸体）”。通过对比增量的 [爆仓L/S比] 和存量的 [持仓L/S比]：
发现燃料：当一方大量浮亏且极度拥挤时，识别潜在的轧空动能。
确认衰竭：当某方向爆仓量占据绝对统治地位时（燃料烧尽），AI 将其识别为动能枯竭的转折点，并果断停止追杀/追高。
🎯 业务价值 (Business Value / Impact)
降噪与防“飞刀”：摒弃散户追涨杀跌的弱逻辑条件反射。
更高的鲁棒性 (Robustness)：无论面对牛市逼空还是熊市流动性枯竭，AI 都能基于“谁在盈利、谁在爆仓”的底层逻辑推理出正确的生存策略，而非寄希望于写死在代码里的指标数值。
这些“Prompt Engineering”的迭代不再是字词的修饰，而是系统交易哲学的重铸，大大缩小了其与顶尖人工交易员在分析宏观复杂局面时的差距。

---

### 🔵 Issue #13: 3月18日 系统升级核心 Issue 修复报告

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-18  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/13

Issue 1：量化大脑“断网”，Qlib 主力模型强制苏醒

病因： 系统之前的特征数据库（qlib_data）永远停留在了两个月前（1月26日），导致真正的机器学习大模型（LightGBM）直接因为数据太旧而拒绝工作。机器人这段时间一直是在用简陋的大数据备胎公式在盲打。
修复成果： 编写了全自动补断脚本，成功把过去 2 个月的数千条 K 线和 158 维变量无缝填平！Qlib 主脑重见天日，目前已百分百在实盘接管交易策略！
Issue 2：突破微软量化底层框架，修复 4H 级别时间戳崩塌

病因： 原本微软 Qlib 官方底层转换工具（

dump_bin
）默认是为传统炒股（收日线）设计的。它会强行把我们从 OKX 取回来的 4H 线（一天 6 次）当成是一天的数据，导致当天多次时间戳冲突闪退（Index 1948 out of bounds）。
修复成果： 绕过了原生限制，重写编写了高精度二阶转换器 

run_dump.py
，打入了 %Y-%m-%d %H:%M:%S 的时间骨架。让 Qlib 完美且精确地兼容了加密货币中最重要的 "4 小时对角线"。
Issue 3：解决“垃圾数据进垃圾出”惨案（DOGE 异常强平复盘）

病因： 初期唤醒 Qlib 时由于偷懒没去抓极其消耗接口请求的“真实历史费率”，系统用 0 做了占位。结果由于假数据掩盖了资金盘风险，导致 Qlib 看到 DOGE 一根阳线就盲目给出了全服第二的看多高分，使得 Agent 被狗庄猎杀。
修复成果（史诗加强）： 彻底根治了基建！重新写了一套高级对齐算法，强行跨接口将真实的 OKX 费率历史（Funding Rate）和合约持仓异动（OI）在纳秒级完美缝合进对应的 4H 级别决策线里。重跑真实数据后，Qlib 瞬间恢复清醒，对 DOGE 的好感度从极度危险的 +0.58 直接悬崖腰斩至 +0.01 拒接接单区间，防线重新生效。
Issue 4：实现 100% 智械闭环（斩断人工强依赖）

病因： 必须得人为手动作业去跑脚本才能为 Qlib 模型续命，这种机制下很容易再出现“忘更两个月”的故障。
修复成果： 大刀阔斧修改了 

run_loop.py
。每当 4 小时 K 线收盘、机器人在做开仓判断前，都会先自动触发一轮数据爬取与数据清洗。保障每一笔多空指令投递前，大脑拿到的都是全世界最新鲜、滚烫的顶级风控数据。

---

### 🔵 Issue #14: 大脑强制进化 (Qlib 模型失效)

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-19  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/14

问题：AI 模型的记忆停留在 2025 年 11 月，完全没有见过 2026 年这波 $7w+ 的大波动，导致在最近的跌市中反复“盲目抄底”。
修复：编写了 

train_local_brain.py
，将模型训练数据同步至 2026-03-19（包含今天的最新跌幅）。
成果：新模型对 BTC 的评分从之前的“盲目自信 (0.8+)”回归到了“冷静观察 (0.57)”。
2. 自动进化逻辑 (无人值守优化)
问题：模型需要手动训练，容易随着时间推移再次产生“数据断层”。
修复：在主循环 

run_loop.py
 中集成了每周自动重训练逻辑。
成果：系统现在设定为每周一凌晨 04:00 自动开启深度学习模式，实现“自我迭代”。
3. 元数据硬编码 (误导性日志修复)
问题：

inference_qlib_model.py
 里的 trained_until 是写死的文字列，即便换了脑子，日志里还会显示它是 2025 年的。
修复：改为动态读取 .pkl 模型文件的真实修改时间。
成果：生成的 

deepseek_payload.json
 能够真实反映模型的“新鲜度”，为后续分析提供可靠依据。
4. 账户状态与行情“断链” (同步隔离修复)
问题：本地 

portfolio_state.json
 与 OKX 实盘持仓存在严重冲突（本地显示空单，实盘是多单）；且 Qlib K 线数据库存在 8 天的数据缺口。
修复：执行了三位一体强制对齐（Local + GitHub + OKX + Qlib Data）。
成果：现在所有维度的行情和持仓数据已 100% 同步。
5. 系统并发稳定性 (Multiprocessing 崩溃修复)
问题：由于 Python 在 macOS 下多进程启动模式（Spawn/Fork）的问题，导致 

run_loop.py
 在训练时频繁报错。
修复：对训练脚本进行了 if __name__ == "__main__": 规范化改造。
成果：主循环运行更加稳健，不再因并发冲突而挂掉。
📈 当前系统状态概览：
大脑版本：V2 (2026-03-19 实测版)
部署环境：Railway 云端 (已同步接收最新推送)
核心安全期：AI 正处于下跌后的“冷静观察期”，Qlib 评分已由乐观转为中性偏谨慎。

---

### 🔵 Issue #15: [Dolores 升级 v2.1 总结报告]：Qlib 复活、风控盾 v2 与 仓位管理全自动化

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-23  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/15

1. 解决核心缺陷 (Core Fixes)
Qlib 复位：修复了特征数量不匹配（12 变为 15）的 Bug，同步了训练与推理的特征库（

qlib_config.py
），并补齐了 5 天断流数据。
周一自动净化：在 

run_loop.py
 加入了 Step 0 逻辑，每逢周一自动触发模型重训，无需人工点火。
2. 注入“盈亏比金律” (RRR > 1.5)
代码拦截：在 

ai_trader.py
 强行植入 1.5 倍盈亏比拦截。就在刚才，它精准拦截了一个 1.1 倍的 ETH 多单，保住了本金。
自审意识：AI 现在在开口建议前，必须在理由里算一遍 期望盈利 / 潜在亏损，只有自己觉得划算（> 1.5x）才准报单。
3. 植入“2% NAV 资产红线” (Risk Management)
风险定价：建立公式：

(开仓总额 × 止损 %) ≤ (总资产 $3,843 × 2%)
。
成果反馈：刚才那笔 BTC 的 100U 保证金正是由于止损设在 15% 处，被系统为了保住 2% 回撤红线“强行瘦身”后的结果。
4. 彻底“断奶”与自主权回归
废除死板模板：删除了提示词里所有 $500 或 3x 杠杆 的固化数字，防止 AI 机械模仿。
动态分配：AI 现在必须根据目前的 $3,843 实收现金，自主决定每一单的投入产出比。
5. 系统稳健化 (Infrastructure)
Git 瘦身：清理了 170 多个二进制碎文件，加速部署。
实时同步：增加了 10 分钟一次的后台历史同步，网页数据与 OKX 实现准实时对齐。

---

### 🔵 Issue #16: Dolores” AI 交易系统加固与逻辑优化

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-25  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/16

1. 幽灵通知拦截 (Ghost Notifications Fix)
问题：即使 OKX 已自动止损，AI 启动时仍会发送重复且无理由的“已平仓”提醒。
优化：加装了执行校验器。现在 AI 必须先获得 OKX 服务器返回的真实成交 ID (Order ID) 才会触发 Telegram 通知，彻底杜绝了虚假提醒。
2. 离场理由自动回填 (Closing Rationale Hardening)
问题：部分平仓动作没有解释理由，用户不知道为什么卖。
优化：建立了“强制回填”机制。如果 AI 在决策中漏掉理由，系统会自动提取开仓时设定的**“认错红线”原话**作为理由发给用户，确保每一笔交易都“事出有因”。
3. 币种变量污染修复 (Symbol Scoping Fix)
问题：心跳总结报告中，不管分析哪个币，底部显示全是 ETH。
优化：修复了报告循环中的局部变量作用域冲突，目前总结报告已能准确区分 BTC, SOL, BNB, DOGE 等各个币种。
4. 交易频率提速 (2H Cycle Upgrade)
需求：由 4 小时运行一次提高到 2 小时运行一次。
优化：更新了 run_loop.py并重新对齐了整点。现在系统会精准对齐到 0, 2, 4, 6... 等偶数点运行，极大提高了对“插针”行情和趋势反转的捕捉速度。
5. 版本追踪体系 (Deployment Versioning)
优化：在 Telegram 报告页脚增加了版本号（如 v2026.03.25.1225）。这能让在 Railway 部署后立刻通过手机确认新代码是否已经生效，避免被旧代码的残留消息误导。
6. 启动逻辑透明化 (Startup Alignment)
澄清：排查并解释了 7:16 异常运行的成因（Railway 部署即运行），并优化了后台日志，区分“启动初测”与“标准周期运行”，消除了时间差上的误解。
7. QLib 健壮性核验 (Quant Verification)
验证：手动触发了 QLib 深度推理任务，确认了模型并无“数值卡死”Bug，目前的分数低迷是模型对低波动横盘行情的真实（保守）反映。

---

### 🔵 Issue #17: AI 计算错误bug优化

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-25  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/17

<h3 id="user-content--本次修改汇总ai_traderpy" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); font-size: 0.875rem; font-weight: 500; margin-top: 0.5rem !important; margin-right: 0px; margin-bottom: 0.25rem !important; margin-left: 0px; color: rgb(204, 204, 204); font-family: -apple-system, &quot;system-ui&quot;, sans-serif; font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; white-space: normal; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;">✅ 本次修改汇总（<span class="context-scope-mention" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); user-select: text !important;"><span class="inline-flex items-center gap-0.5 rounded-md align-middle text-sm font-medium transition-[opacity,background-color] cursor-pointer hover:bg-gray-500/20 select-text translate-y-[-1px]" draggable="true" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: -1px; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; display: inline-flex; transform: translate(0px, -1px) rotate(0deg) skew(0deg, 0deg) skewY(0deg) scaleX(1) scaleY(1); cursor: pointer; user-select: text !important; align-items: center; gap: 0.125rem; border-radius: 0.375rem; vertical-align: middle; font-size: 0.813rem; font-weight: 500; transition-property: opacity, background-color; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1); transition-duration: 0.15s; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); padding: 1px 0.25rem 1px 0.125rem;"><div style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); user-select: text !important;"><img src="vscode-file://vscode-app/Applications/Antigravity.app/Contents/Resources/app/extensions/theme-symbols/src/icons/files/python.svg" width="16px" height="16px" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border: 0px; display: inline-block; vertical-align: middle; max-width: 100%; height: auto; user-select: text !important; min-width: 16px; min-height: 16px; transform: translateY(-1px);"></div><span class="inline-flex break-all leading-tight" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; display: inline-flex; word-break: break-all; line-height: 1.25; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); user-select: text !important;">ai_trader.py</span></span></span>）</h3><p node="[object Object]" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); margin: 0px; color: rgb(204, 204, 204); font-family: -apple-system, &quot;system-ui&quot;, sans-serif; font-size: 13.008px; font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; white-space: normal; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;"><strong style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); font-weight: bolder;">改动 1：Temperature 设置</strong></p><pre style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, &quot;Liberation Mono&quot;, &quot;Courier New&quot;, monospace; font-feature-settings: normal; font-variation-settings: normal; font-size: 13.008px; margin: 0px; color: rgb(204, 204, 204); font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;"><div node="[object Object]" class="relative whitespace-pre-wrap word-break-all my-2 rounded-lg bg-list-hover-subtle border border-gray-500/20" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; position: relative; margin-top: 0.5rem; margin-bottom: 0.5rem; white-space: pre-wrap; border-radius: 0.5rem; border-width: 1px; border-color: rgba(107, 114, 128, 0.2); background-color: rgba(42, 45, 46, 0.5); box-sizing: border-box; border-style: solid;"><div class="min-h-7 relative box-border flex flex-row items-center justify-between rounded-t border-b border-gray-500/20 px-2 py-0.5" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; position: relative; box-sizing: border-box; display: flex; min-height: 1.75rem; flex-direction: row; align-items: center; justify-content: space-between; border-top-left-radius: 0.25rem; border-top-right-radius: 0.25rem; border-width: 0px 0px 1px; border-color: rgba(107, 114, 128, 0.2); padding: 0.125rem 0.5rem; border-style: solid;"><div class="font-sans text-sm text-ide-text-color opacity-60" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; font-family: ui-sans-serif, system-ui, sans-serif, &quot;Apple Color Emoji&quot;, &quot;Segoe UI Emoji&quot;, &quot;Segoe UI Symbol&quot;, &quot;Noto Color Emoji&quot;; font-size: 0.813rem; opacity: 0.6; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235);"></div><div class="flex flex-row gap-2 justify-end" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; display: flex; flex-direction: row; justify-content: flex-end; gap: 0.5rem; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235);"></div></div><div class="p-3" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; padding: 0.75rem; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235);"><div class="w-full h-full text-xs cursor-text" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; height: 17.8874px; width: 230.897px; cursor: text; font-size: 0.688rem; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235);"><div class="code-block" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); font-family: monospace; font-size: inherit;"><div class="code-line" data-line-number="1" data-line-start="1" data-line-end="1" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); display: flex; min-height: 1.2em;"><div class="line-content" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); flex: 1 1 0%; white-space: pre-wrap; word-break: break-word;"><span class="mtk1" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); color: rgb(204, 204, 204);">temperature=0.5   ← 新增</span></div></div></div></div></div></div></pre><p node="[object Object]" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); margin: 0px; color: rgb(204, 204, 204); font-family: -apple-system, &quot;system-ui&quot;, sans-serif; font-size: 13.008px; font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; white-space: normal; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;">在创意性（1.5）和数学严谨性（0.0）之间取中，不死板、不发散。</p><p node="[object Object]" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); margin: 0px; color: rgb(204, 204, 204); font-family: -apple-system, &quot;system-ui&quot;, sans-serif; font-size: 13.008px; font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; white-space: normal; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;"><strong style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; box-sizing: border-box; border-width: 0px; border-style: solid; border-color: rgb(229, 231, 235); font-weight: bolder;">改动 2：提示词变量语义锁定</strong></p><div class="my-4 rounded-lg overflow-x-auto overflow-y-hidden border border-gray-500/20 [&amp;_thead_tr:first-child_th:first-child]:border-t-0 [&amp;_thead_tr:first-child_th:first-child]:border-l-0 [&amp;_thead_tr:first-child_th:last-child]:border-t-0 [&amp;_thead_tr:first-child_th:last-child]:border-r-0 [&amp;_tbody_tr:last-child_td:first-child]:border-b-0 [&amp;_tbody_tr:last-child_td:first-child]:border-l-0 [&amp;_tbody_tr:last-child_td:last-child]:border-b-0 [&amp;_tbody_tr:last-child_td:last-child]:border-r-0 [&amp;_thead_tr:first-child_th]:border-t-0 [&amp;_tbody_tr:last-child_td]:border-b-0 [&amp;_th:first-child]:border-l-0 [&amp;_td:first-child]:border-l-0 [&amp;_th:last-child]:border-r-0 [&amp;_td:last-child]:border-r-0" style="--tw-border-spacing-x: 0; --tw-border-spacing-y: 0; --tw-translate-x: 0; --tw-translate-y: 0; --tw-rotate: 0; --tw-skew-x: 0; --tw-skew-y: 0; --tw-scale-x: 1; --tw-scale-y: 1; --tw-pan-x: ; --tw-pan-y: ; --tw-pinch-zoom: ; --tw-scroll-snap-strictness: proximity; --tw-gradient-from-position: ; --tw-gradient-via-position: ; --tw-gradient-to-position: ; --tw-ordinal: ; --tw-slashed-zero: ; --tw-numeric-figure: ; --tw-numeric-spacing: ; --tw-numeric-fraction: ; --tw-ring-inset: ; --tw-ring-offset-width: 0px; --tw-ring-offset-color: #fff; --tw-ring-color: rgb(67 128 180 / .5); --tw-ring-offset-shadow: 0 0 #0000; --tw-ring-shadow: 0 0 #0000; --tw-shadow: 0 0 #0000; --tw-shadow-colored: 0 0 #0000; --tw-blur: ; --tw-brightness: ; --tw-contrast: ; --tw-grayscale: ; --tw-hue-rotate: ; --tw-invert: ; --tw-saturate: ; --tw-sepia: ; --tw-drop-shadow: ; --tw-backdrop-blur: ; --tw-backdrop-brightness: ; --tw-backdrop-contrast: ; --tw-backdrop-grayscale: ; --tw-backdrop-hue-rotate: ; --tw-backdrop-invert: ; --tw-backdrop-opacity: ; --tw-backdrop-saturate: ; --tw-backdrop-sepia: ; --tw-contain-size: ; --tw-contain-layout: ; --tw-contain-paint: ; --tw-contain-style: ; border-style: solid; border-color: rgba(107, 114, 128, 0.2); margin-top: 1rem; margin-bottom: 1rem; overflow: auto hidden; border-radius: 0.5rem; border-width: 1px; box-sizing: border-box; color: rgb(204, 204, 204); font-family: -apple-system, &quot;system-ui&quot;, sans-serif; font-size: 13.008px; font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; letter-spacing: normal; orphans: 2; text-align: start; text-indent: 0px; text-transform: none; widows: 2; word-spacing: 0px; -webkit-text-stroke-width: 0px; white-space: normal; background-color: rgb(37, 37, 38); text-decoration-thickness: initial; text-decoration-style: initial; text-decoration-color: initial;">
原来（模糊） | 现在（清晰）
-- | --
Available SHORT Room | [REMAINING BUDGET - NOT THE CEILING]
DO NOT exceed the Available Room | DO NOT exceed the GLOBAL CEILING
(无规则) | ⚠️ 强制公式：必须用 USAGE / CEILING，严禁用 USAGE / REMAINING

</div>

---

### 🔵 Issue #18: 🛡️ Issue Fix: AI 自生成低 RRR 开仓信号却未自我拦截

> **状态**: OPEN  
> **标签**: 无  
> **创建时间**: 2026-03-25  
> **链接**: https://github.com/yuqiaowu/whale-watcher/issues/18

**日期**: 2026-03-25 | **Commit**: `681dbe4` | **状态**: ✅ 已修复

## 根因

| # | 问题 | 原因 |
|---|------|------|
| 1 | AI 知道 RRR=1.33 却仍输出 `open_short` | 提示词只描述规则，没说"违规了必须输出 `monitor`" |
| 2 | TP/SL 缺失时 RRR 检查被静默跳过 | Python 验证器 `if tp > 0 and sl > 0` 的 else 分支是空的，开仓直接放行 |

## 修复

**Fix 1 — 提示词层**：将 RRR 规则改写为强制行为指令 `"HARD GATE — SELF-ENFORCE BEFORE OUTPUT"`，明确规定 RRR < 1.5 时必须输出 `monitor`，否则视为 `LOGICAL INTEGRITY BREACH`

**Fix 2 — Python 验证层**：补充 `else` 分支，对 TP/SL 缺失的 `open_` 动作直接 `REJECTED`，不再静默放行

## 双重防线架构

```
AI 输出 JSON
  │
  ▼ 第一道：提示词自检（RRR < 1.5 → 输出 monitor）
  │
  ▼ 第二道：Python validate_and_enforce_decision()
     ├── TP/SL 缺失 → REJECTED  ← 新增
     ├── RRR < 1.45 → REJECTED
     └── NAV Risk > 2% → 调整 size
```

---
