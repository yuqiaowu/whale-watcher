# AI Crypto Terminal 前端 PRD

## 1. 背景

当前后端已经形成一条可审计交易链路：宏观与链上数据刷新、Qlib 模型推理、DeepSeek 模型方向判断、程序风控审核、执行层、持仓运行期管理、交易记录持久化。

前端目标不是做一个“炫酷行情页”，而是做一个能回答关键问题的交易中控台：

- 现在市场宏观和流动性到底偏多还是偏空？
- 这个判断相比上一轮发生了什么边际变化？
- 当前持有哪些仓位，盈利/亏损如何，是否接近平仓或减仓条件？
- 最新一轮模型和规则层做了什么决定，为什么开仓/不开仓/平仓/减仓？
- 历史订单表现如何，收益曲线相对 BTC 基准是否有效？
- 能否基于历史订单重新回测，验证策略或某类信号是否值得继续保留？

## 2. 产品目标

### 2.1 核心目标

1. 展示系统当前状态：数据新鲜度、模型新鲜度、运行模式、执行模式。
2. 展示宏观、流动性、链上、技术、Qlib、模型决策的完整因果链。
3. 展示持仓、订单、盈亏、开平仓理由和运行期处理动作。
4. 展示账户收益曲线，并与 BTC buy-and-hold 基准对比。
5. 支持基于历史订单进行回测计算和策略复盘。
6. 提供赞赏入口，支持 SOL 地址和支付宝二维码/账号。

### 2.2 非目标

- 前端不直接生成交易信号。
- 前端不直接修改模型判断、仓位、杠杆、止损、止盈。
- 前端不展示隐藏推理链、API Key、Mongo URI、OKX Secret。
- 前端不把模型方向判断包装成确定性投资建议。

## 3. 目标用户

### 3.1 系统所有者

关注实盘是否按预期运行、数据是否新鲜、仓位是否安全、模型是否在胡说、为什么没有开仓或为什么触发了减仓/平仓。

### 3.2 观察者 / 订阅用户

关注当前市场判断、持仓表现、历史收益、订单逻辑和策略可信度。

## 4. 信息架构

建议采用 6 个主页面：

1. **总览 Dashboard**
2. **宏观与流动性 Macro & Liquidity**
3. **决策中心 Decision Center**
4. **持仓与执行 Positions & Runtime**
5. **历史订单 Orders**
6. **回测与复盘 Backtest Lab**

辅助页面：

7. **系统健康 System Health**
8. **赞赏 Support**

## 5. 页面 PRD

## 5.1 总览 Dashboard

### 用户问题

- 今天系统整体是 risk-on 还是 risk-off？
- 当前有没有持仓？赚了还是亏了？
- 最新 cycle 有无开仓/平仓/减仓？
- 系统数据和模型是否新鲜？
- 账户收益是否跑赢 BTC？

### 核心模块

#### A. 顶部状态栏

字段：

- `latest_decision_cycle_v2.cycleId`
- `generated_at_local`
- `decision_mode`
- `TRADING_MODE`
- `ENABLE_V2_EXECUTION`
- `MODEL_DECISION_MODE`
- `qlib_freshness.fresh`
- `qlib_freshness.model_is_fresh`
- `latest_system_run.qlib_retrain.policy`
- `latest_system_run.qlib_retrain.needed`
- `latest_system_run.qlib_retrained`
- Mongo DB target，例如 `whale_watcher_real`

展示方式：

- 绿色：数据新鲜 + 模型新鲜 + cycle 正常
- 黄色：模型关闭、执行关闭、部分数据缺失
- 红色：Qlib stale、Mongo 不可用、cycle 超过预期时间未更新

说明文案：

- “Qlib 数据/推理每轮刷新；Qlib 模型参数默认按重训策略更新，通常不是每轮重训。”

#### B. 账户概览卡

字段：

- `portfolio_state.total_equity`
- `portfolio_state.cash`
- `portfolio_state.positions.length`
- 当日 PnL
- 累计 PnL
- 最大回撤
- 胜率
- Profit factor

#### C. 收益曲线

展示：

- 账户净值曲线
- BTC buy-and-hold 基准曲线
- 超额收益曲线：账户收益 - BTC 收益
- 最大回撤阴影
- 关键交易点：开仓、减仓、平仓

数据来源：

- `nav_history`
- `trade_history`
- BTC 价格序列，可来自 Qlib feature CSV 或行情接口缓存

#### D. 最新决策摘要

按币种展示：

- symbol
- action / direction
- confidence
- risk_level
- summary
- trade_plan_count
- final_intent
- execution_action
- order_status
- failure_reason

重点文案：

- “模型只判断方向；仓位、杠杆、止损、止盈由程序控制。”

## 5.2 宏观与流动性 Macro & Liquidity

### 用户问题

- 当前宏观是 risk-on、neutral 还是 risk-off？
- 流动性是在改善还是恶化？
- 边际变化是什么？
- 宏观最终判断是程序给的、模型给的，还是二次 adjudication 后的？

### 核心模块

#### A. 当前宏观状态

字段：

- `macro_mode`
- `macro_permission`
- `macro_bias_tier`
- `macro_impact_score`
- `macro_horizon`
- `final_macro_decision.market_impact`
- `final_macro_decision.impact_horizon`
- `final_macro_decision.crypto_relevance`
- `final_macro_decision.confidence`
- `macro_decision_source`

展示建议：

- 使用 4 档或 5 档视觉状态：
  - Strong Risk-On
  - Mild Risk-On
  - Neutral / Allow Both
  - Mild Risk-Off
  - Strong Risk-Off

#### B. 流动性变化

字段：

- stablecoin net flow
- token net flow
- VIX
- Fear & Greed
- DXY / rate / labor data，如果后端有
- funding_rate
- funding_zscore
- open interest
- liquidation long/short ratio

展示：

- 最近 24h / 7d / 30d 趋势图
- 当前值
- 上一周期值
- 边际变化：`delta`
- 变化方向：improving / deteriorating / neutral

#### C. 边际变化解释

目标：不要只显示“RISK_OFF”，要显示为什么变化。

字段建议：

- `marginal_tags`
- `key_tags`
- `brief_rationale`
- `previous_macro_mode`
- `current_macro_mode`
- `macro_impact_score_delta`
- stablecoin flow delta
- VIX delta
- funding zscore delta

展示文案示例：

> 宏观仍为 RISK_OFF，但边际压力较上一轮减弱：VIX 下行，stablecoin outflow 收窄，Qlib flat 概率上升。

#### D. 对交易的影响

展示宏观不直接决定模型是否产生交易意图，而是影响：

- 仓位
- 杠杆
- 方向权限
- 风险折扣
- 是否允许 LONG / SHORT / BOTH

字段：

- `macro_permission`
- `riskReview.review_note`
- `approved_risk_fraction`
- `macro conflict reduced size`

## 5.3 决策中心 Decision Center

### 用户问题

- 每个币当前模型怎么看？
- 为什么不开仓？
- 如果开仓，失效条件是什么？
- 程序有没有采纳模型给出的失效条件？
- 最终是模型决定、规则层决定，还是风控层拦截？

### 核心模块

#### A. Symbol 决策列表

每个 symbol 一行：

- symbol
- price
- price_source
- stale_market_price_replaced
- Qlib rank
- `p_up_8h / p_down_8h / p_flat_8h`
- model action / direction
- confidence
- trade_plan_count
- verifier / risk review passed
- final_intent
- execution_action

#### B. 单币详情抽屉

分 6 个 Tab：

1. Market State
2. Model Decision
3. Trade Plan
4. Risk Review
5. Execution
6. Audit Trail

#### C. Market State Tab

展示：

- 技术指标：
  - current_price
  - RSI
  - Williams %R
  - Bollinger position
  - SMA50 / SMA200 distance
  - MA structure：SMA5 / SMA10 / SMA50 / SMA200、MA cross、price vs SMA200
  - MACD：macd line / signal / histogram / cross up / cross down
  - ATR
  - 120d drawdown
  - regime_1d
  - major_trend_1d
- Qlib：
  - rank
  - percentile
  - p_up / p_down / p_flat
  - direction
  - freshness
  - 概率解释：`p_down_8h = 0.862` 表示从决策时点往后 8 小时下跌概率约 86.2%，不是开仓后已经实现的收益，也不是保证会跌。
- 链上：
  - `flow_data_available`
  - token_net_flow
  - stablecoin_net_flow
  - flow_composite_semantic
  - exchange_netflow_24h
  - large_transfer_count_24h
  - whale_bias
  - flow_bias
  - funding
  - OI
  - liquidation ratios
- 数据覆盖：
  - `data_availability.has_onchain_flow_data`
  - `data_availability.has_exchange_netflow_24h`
  - `data_availability.has_large_transfer_count_24h`
  - `data_availability.has_rsi14`
  - `data_availability.has_williams_r14`
- 宏观：
  - macro_mode
  - macro_permission
  - macro_bias_tier

#### D. Model Decision Tab

展示：

- `action`
- `direction`
- `confidence`
- `risk_level`
- `setup_type`
- `horizon`
- `reason_codes`
- `summary`
- `invalid_if`
- `invalidation_rules`
- `llm_audit.reasoner.status`
- `llm_audit.formatter.status`
- `llm_audit.verifier.status`
- `llm_audit.reasoner.attempt_count`
- `verifier.veto`
- `verifier.veto_reasons`
- `verifier.missing_data`
- `verifier.risk_notes`

Verifier 展示规则：

- `veto_reasons`：真正导致否决的原因，例如 Qlib stale、技术面明显矛盾、方向与市场状态冲突。
- `missing_data`：数据缺口或覆盖限制，只作为风险提示展示。
- 如果 DOGE / BNB / BTC 等 symbol 没有链上流覆盖，`exchange_netflow_24h`、`large_transfer_count_24h`、`whale_bias`、`flow_bias` 缺失不应展示成硬否决。
- 前端文案要区分“模型主动 WAIT/FLAT”和“verifier 否决后 fallback WAIT/FLAT”。

不展示：

- 完整 hidden reasoning
- 完整 prompt
- API 响应原文长文本

真实字段说明：

- `modelDecision.action` 使用 `BUY / SELL / WAIT / HOLD`。
- `modelDecision.direction` 使用 `LONG / SHORT / FLAT`。
- 前端可将 `BUY + LONG` 展示为 `OPEN_LONG 意图`，将 `SELL + SHORT` 展示为 `OPEN_SHORT 意图`，但不要误以为模型直接控制下单。
- `modelDecision.model_role = direction_only` 时，必须展示“模型只给方向，程序控制仓位/杠杆/止损/止盈/执行”。

#### E. Trade Plan / Risk Review Tab

展示：

- `model_trade_plan`
- model action：BUY / SELL / WAIT / HOLD
- execution action：OPEN_LONG / OPEN_SHORT / START_GRID_BOT / DO_NOTHING
- direction
- entry_type
- stop_loss / take_profit
- max_holding_bars
- `model_approved_invalidation_rules`
- `model_rejected_invalidation_rules`
- rejected reason
- `rule_trace`
- `reason_codes`

核心解释：

- 最新版本不再依赖策略层先生成候选交易。模型直接输出交易动作和方向，程序只负责风控审核、仓位/杠杆、止损止盈、失效条件白名单、verifier 二次审核和执行。
- 模型可以提出 `invalidation_rules`，程序只采纳白名单字段和合理方向的规则。
- 后端兼容字段仍叫 `candidate.candidate_proposals`，但当 `candidate.generation_mode = model_decision` 时，前端产品文案应展示为“模型交易计划”。

#### F. Risk / Execution Tab

展示：

- approved / rejected
- final_intent
- approved_position_size_usd
- leverage
- position_notional_usd / margin_usd 必须分开展示：
  - `position_notional_usd` = 当前币数量 * 当前价格，代表真实名义敞口
  - `margin_usd` = 交易所保证金占用，不能当作仓位金额
- stop_loss
- take_profit
- max_holding_bars
- 仓位与敞口规则：
  - 普通方向单默认名义仓位：账户净值 * 25%
  - 普通方向单单笔硬上限：账户净值 * 40%
  - 全账户总名义敞口硬上限：账户净值 * 75%
  - 单笔最大亏损仍受 `approved_risk_fraction = 2%` 约束，止损距离过大时优先降仓位
- risk_level 对应参数：
  - DEFAULT：基准 5x，最多 3 根 4H bar
  - MEDIUM：降到 3x，最多 2 根 4H bar
  - LOW：降到 2x，最多 1 根 4H bar
- 生效范围：以上为新系统后续订单规则；历史遗留仓位按其原始记录或接管后的 runtime 规则展示。
- execution_action
- order_status
- failure_reason
- exchange_order_id
- clOrdId / ordId / order tag
- protection_status

## 5.4 持仓与执行 Positions & Runtime

### 用户问题

- 现在持有什么？
- 赚亏多少？
- 到没到止损/止盈/减仓/平仓条件？
- 当前持仓的 thesis 是否还有效？

### 核心模块

#### A. 当前持仓表

字段：

- symbol
- side
- entryPrice
- currentPrice
- amount / size
- leverage
- margin
- unrealized PnL
- unrealized PnL %
- stopLoss
- takeProfit
- holding time
- position source：new / adopted / reconciled
- provenance status：
  - `MATCHED_BY_CLORDID`
  - `MATCHED_BY_ORDID`
  - `MATCHED_BY_TIME_PRICE`
  - `ADOPTED_LIVE_POSITION`
  - `UNMATCHED_LIVE_POSITION`
- cycleId / intent / order tag

#### B. 持仓 thesis / invalidation

字段：

- `invalidation_rule.zh`
- `invalidation_rule.conditions`
- runtime 最新判断：
  - triggered / not triggered
  - trigger reason
  - trigger field
  - trigger value
- thesis 来源：
  - 原始 modelDecision / riskReview / verifier / rule_trace
  - provenance 匹配失败时展示“原始开仓 thesis 不可用，当前由 runtime fallback / SL / TP 管理”

#### C. 最大持仓与到期 review

前端必须展示“到期”不是无条件强平，而是一个 review 节点：

- runtime guard：约每 10 分钟扫描当前持仓、止损止盈、失效条件和风控状态。
- thesis review：基于 4H bar 的订单，到最大持仓窗口后 review，不做每小时完整重算。
- 到最大持仓时间时：
  - 如果已经盈利：优先获利平仓，runtime reason 为 `max_holding_profit_take` / `MAX_HOLDING_PROFIT_TAKE_TRIGGERED`。
  - 如果没有盈利：做一次完整 thesis review。
  - 如果 thesis 仍成立：只延长 1 根 4H bar，并记录下一次 review 时间。
  - 如果 thesis 不成立：平仓或按 runtime action 减仓。
- 前端字段：
  - max_holding_bars
  - holding_window_started_at
  - max_holding_due_at
  - next_review_at
  - extension_count
  - latest_review_result
  - latest_review_reason

#### D. Runtime 动作流

展示：

- HOLD
- REDUCE_25
- REDUCE_50
- CLOSE
- THESIS_WEAKENED_TRIGGERED
- INVALIDATION_TRIGGERED
- MAX_HOLDING_PROFIT_TAKE_TRIGGERED

数据来源：

- `trade_decision_records`
- `position_runtime.py` 写入的 runtime history / evaluation 字段
- `trade_history`
- `portfolio_state` 当前实盘仓位快照
- OKX order / fill history reconciliation

## 5.5 历史订单 Orders

### 用户问题

- 系统过去开过哪些单？
- 每单为什么开，为什么平？
- 盈亏如何？
- 哪类理由最赚钱，哪类理由最亏？

### 核心模块

#### A. 历史订单表

字段：

- decisionId
- cycleId
- symbol
- side
- strategy_family
- trigger_source
- open time
- close time
- entry
- exit
- size
- leverage
- stop_loss
- take_profit
- realized PnL
- PnL %
- holding duration
- order_status
- close_reason
- runtime_reason
- reconciliation_status
- source：new / adopted / reconciled / unmatched_closed
- provenance match method：clOrdId / ordId / time_price / adopted / unmatched
- opening decision available：yes / no
- verifier decision available：yes / no

筛选：

- symbol
- side
- strategy_family
- trigger_source
- model / legacy
- profitable / losing
- open / closed
- date range
- macro_mode
- qlib direction
- reason_codes

#### B. 开仓理由

展示：

- modelDecision summary
- reason_codes
- model_trade_plan
- rule trace
- risk review note
- verifier 结果：
  - approved / veto
  - veto reasons
  - missing data notes
  - risk notes
- Qlib 概率与解释：
  - p_up_8h / p_down_8h / p_flat_8h
  - Qlib direction
  - Qlib freshness

#### C. 平仓/减仓理由

展示：

- runtime reason
- invalidation condition
- max holding review
- profit-first expiry
- manual / reconciliation / exchange reason
- unmatched OKX closed trade reason
- adopted live position close reason
- max holding 到期 review 结论
- thesis extension / invalidation / profit take 的完整事件链

#### D. 订单详情页

建议结构：

1. 基本信息
2. 开仓前市场状态
3. 模型结论
4. 程序规则审核
5. 风控参数
6. 执行回执
7. 持仓期间 runtime 事件
8. 平仓结果
9. reconciliation / adoption 审计
10. 复盘备注

#### E. 开仓来源追溯规则

前端不要只按 symbol 展示订单来源，必须展示订单身份匹配结果：

- 新系统下单时应有 `clOrdId` 或 tag，包含 cycleId、symbol、intent。
- reconciliation 从 OKX order history / fill history 查开仓订单。
- 匹配优先级：
  - clOrdId / tag 精确匹配
  - ordId 匹配
  - symbol + side + open time + entryPrice 近似匹配
- 匹配成功后回填：
  - modelDecision
  - riskReview
  - verifier
  - rule_trace
  - invalidation_rules
- 匹配失败才标记为 `ADOPTED_LIVE_POSITION` 或 `UNMATCHED_LIVE_POSITION`。
- 如果仓位是旧版本开的，前端要明确提示“历史系统开仓，新系统接管管理”，不能伪装成当前模型刚开的单。

## 5.6 回测与复盘 Backtest Lab

### 用户问题

- 如果只做某一类历史订单，收益如何？
- 如果过滤掉低置信度模型单，收益是否更好？
- 如果宏观和技术冲突时不交易，是否能降低回撤？
- 如果调整止盈/止损/持仓周期，结果如何？

### MVP 范围

基于历史订单做“订单级回测”，不是重新跑完整行情级策略。

输入：

- 历史订单：`trade_decision_records`
- 成交结果：`trade_history`
- 净值历史：`nav_history`
- BTC 基准价格

可配置参数：

- symbol filter
- date range
- side：long / short / both
- strategy_family
- trigger_source
- model confidence min
- risk_level
- macro_mode
- macro_permission
- qlib rank range
- qlib p_up / p_down / p_flat threshold
- 是否包含 adopted positions
- 是否包含 execution skipped 的模拟信号

输出指标：

- total return
- CAGR，如果时间跨度足够
- max drawdown
- Sharpe / Sortino，如果有日频或 bar 级净值
- win rate
- profit factor
- average win / average loss
- expectancy
- trade count
- average holding time
- best / worst trade
- long vs short breakdown
- symbol breakdown
- reason_code breakdown

### 进阶回测

行情级回测需要额外能力：

- 每根 bar 重放 snapshot
- 按当时价格模拟 entry / SL / TP
- 手续费、滑点、最小下单数量
- 资金曲线和同时持仓约束
- BTC benchmark 同步 bar

建议作为 Phase 2。

### 回测结果页面

模块：

- 参数面板
- 回测摘要卡
- 收益曲线 vs BTC
- 回撤曲线
- 订单列表
- 按标签归因：
  - model vs legacy
  - macro mode
  - Qlib direction
  - trigger_source
  - reason_codes

## 5.7 系统健康 System Health

### 展示字段

- 最新 `latest_system_run`
- latest cycle age
- Mongo read/write status
- Qlib freshness
- Qlib model freshness
- Qlib retrain policy
- Qlib retrain needed / reasons
- latest Qlib retrain result
- Qlib model trained_at / train_end / data_latest_datetime
- DeepSeek reasoner / formatter 最近成功率
- DeepSeek verifier 最近成功率
- verifier veto count
- verifier missing-data-only downgrade count
- retry count
- OKX mode：SHADOW / DEMO / LIVE
- execution enabled
- open positions count
- last runtime action
- last reconciliation action
- provenance matching health：
  - open positions with matched decision count
  - adopted live positions count
  - unmatched live positions count
  - stale provenance mismatch count
- max holding review health：
  - overdue review count
  - next review time
  - extension count distribution

### 告警

- Qlib stale
- model stale
- Qlib retrain failed
- cycle stale
- Mongo fallback
- DeepSeek 连续失败
- verifier 连续异常或缺失字段误判频繁
- OKX error
- stale market price replacement 频繁发生
- 有实盘仓位但没有可执行失效条件
- 有实盘仓位但找不到原始开仓理由，且未标记为 adopted
- 到期 review 超时未执行
- provenance 只按 symbol 复用，疑似错绑旧订单理由

## 5.8 赞赏 Support

### 目标

允许用户赞赏项目维护者，支持 SOL 地址和支付宝。

### 页面内容

#### A. SOL 赞赏

展示：

- SOL 地址
- QR code
- copy 按钮
- 网络标记：Solana
- 风险提示：请确认网络为 Solana，不要向该地址转入非 Solana 网络资产

字段建议：

```json
{
  "support": {
    "solana_address": "",
    "alipay_qr_url": "",
    "alipay_account_masked": ""
  }
}
```

#### B. 支付宝赞赏

展示：

- 支付宝二维码
- 可选展示脱敏账号
- “仅用于赞赏，不构成投资服务购买”提示

#### C. 赞赏记录

MVP 不需要记录链上或支付宝赞赏历史。后续可支持：

- 用户留言
- 赞赏榜
- 链上交易 hash 填写

## 6. 数据来源与接口

## 6.1 当前后端已存在 API

当前前端应优先基于这些真实接口接数据，不要假设 `/api/dashboard` 已经存在。

### GET `/api/summary`

返回账户摘要：

- nav
- initialNav
- totalPnl
- pnlPercent
- startTime
- winRate
- totalTrades

### GET `/api/positions`

返回 OKX / portfolio_state 当前持仓快照：

- symbol
- type / posSide
- entryPrice
- currentPrice
- stopLoss
- takeProfit
- amount
- pnl
- pnlPercent
- leverage

### GET `/api/history`

返回最近历史成交：

- id
- symbol
- type
- entryPrice / exitPrice
- entryTime / exitTime
- pnl / pnlPercent
- leverage

### GET `/api/nav-history`

返回净值曲线。BTC 基准可来自返回的 `btc_price`，没有时前端需要使用行情缓存或后端补齐。

### GET `/api/v2/latest-cycle`

返回最新 V2 决策周期：

- cycleId
- generated_at / generated_at_local
- decision_mode：`model_decision` 或 `candidate_blueprint`
- qlib_freshness：
  - fresh
  - expected_completed_bar
  - payload_as_of
  - model_trained_at
  - model_train_end
  - model_is_fresh
  - model_freshness_reason
  - missing_payload_symbols
  - stale_csv_symbols
  - reasons
- snapshots
- candidate_batches
- rule_evaluations
- research_outputs
- risk_reviews
- executions
- post_trade_review

说明：即使 `decision_mode = model_decision`，后端为了复用风控执行链，仍会生成 `candidate_batches[].candidate_proposals`。前端展示时应命名为“模型交易计划”，不要对用户展示成“策略层 candidate”。

### GET `/api/v2/trade-records`

返回最近 `trade_decision_records`：

- decisionId
- cycleId
- symbol
- positionState
- marketState
- modelDecision
- candidate.generation_mode
- candidate.candidate_proposals
- candidate.model_decision_diagnostic
- ruleEvaluation
- researchOutput
- riskReview
- execution
- provenance

### GET `/api/v2/latest-trade-record`

返回最新单条 `trade_decision_record`，用于详情页兜底。

### GET `/api/health`

返回运行健康摘要：

- status
- version
- mongo_connected
- latest_run_status
- latest_run_at
- latest_cycle_id

### GET `/api/admin/latest-run`

返回最新系统运行记录，系统健康页可用。

### GET `/api/admin/runs`

返回最近系统运行历史，系统健康页可用。

## 6.2 后续推荐聚合 API

### GET `/api/dashboard`

返回：

- portfolio summary
- latest cycle summary
- latest macro summary
- latest decisions by symbol
- latest runtime actions

### GET `/api/macro`

返回：

- current macro
- liquidity indicators
- marginal changes
- historical macro timeline

### GET `/api/decisions/latest`

返回：

- latest_decision_cycle_v2
- per-symbol modelDecision
- ruleEvaluation
- riskReview
- execution

### GET `/api/positions`

返回：

- portfolio_state.positions
- runtime evaluation
- unrealized PnL
- provenance status and match method
- invalidation rules and executable status
- max_holding_due_at / next_review_at / extension_count

### GET `/api/orders`

参数：

- symbol
- side
- status
- date_from
- date_to
- strategy_family
- trigger_source
- model_only

返回：

- normalized trade decision records
- linked trade history if closed
- order provenance fields：clOrdId / ordId / tag / match_method
- opening modelDecision / riskReview / verifier / rule_trace
- close reason chain and runtime events

### GET `/api/performance`

返回：

- nav curve
- btc benchmark curve
- return metrics
- drawdown

### POST `/api/backtest/orders`

输入：

- filter params
- sizing assumption
- include skipped signal or not
- benchmark

返回：

- metrics
- equity curve
- drawdown curve
- selected trades
- breakdowns

### GET `/api/support`

返回：

- solana_address
- alipay_qr_url
- alipay_account_masked

## 7. 前端组件建议

### 7.1 组件列表

- `SystemStatusBar`
- `PortfolioSummaryCards`
- `EquityCurveWithBenchmark`
- `MacroStateCard`
- `LiquidityDeltaPanel`
- `DecisionTable`
- `DecisionDetailDrawer`
- `PositionTable`
- `RuntimeActionFeed`
- `OrdersTable`
- `OrderDetailDrawer`
- `BacktestParameterPanel`
- `BacktestResultSummary`
- `AttributionBreakdown`
- `SupportPanel`

### 7.2 图表

建议使用：

- 收益曲线：line chart
- 回撤：area chart
- 宏观状态历史：timeline
- Qlib 概率：stacked bar or mini bars
- reason_code 盈亏归因：bar chart
- 持仓盈亏：table + sparkline

## 8. 权限与安全

## 8.0 国际化 i18n

前端需要支持中文和英文两个完整版本，并提供全站语言切换。语言切换不是局部按钮文案翻译，而是整站所有用户可见内容统一切换。

### 基本原则

- 默认根据浏览器语言选择：中文用户显示中文，英文环境显示英文。
- 用户手动切换后写入 localStorage，后续访问保持用户选择。
- 所有页面标题、导航、按钮、表格列名、图表图例、tooltip、空状态、告警、帮助说明都必须走 i18n 字典。
- 后端返回的枚举值不直接裸展示，需要前端通过 enum mapper 转成当前语言文案。
- 金额、百分比、时间、日期保留统一格式化函数，避免中英文页面格式不一致。

### 必须翻译的内容范围

- Dashboard：账户卡片、收益曲线、最新决策摘要、宏观边际摘要。
- Macro & Liquidity：宏观状态、流动性解释、图表图例、边际变化说明。
- Decision Center：模型动作、Qlib 概率解释、verifier 结果、reason_codes、fallback 原因。
- Positions：持仓表、失效条件、runtime action、最大持仓 review 状态。
- Orders：开仓理由、平仓理由、reconciliation / adoption 状态。
- Backtest：参数面板、回测指标、归因标签。
- System Health：健康状态、告警类型、数据新鲜度。
- Support：SOL / 支付宝赞赏文案和风险提示。

### 枚举翻译规则

以下字段必须做 enum mapper：

- modelDecision.action：BUY / SELL / WAIT / HOLD
- execution.execution_action：OPEN_LONG / OPEN_SHORT / START_GRID_BOT / DO_NOTHING
- side：LONG / SHORT
- risk_level：DEFAULT / MEDIUM / LOW
- runtime_reason：INVALIDATION_TRIGGERED / MAX_HOLDING_PROFIT_TAKE_TRIGGERED / THESIS_WEAKENED_TRIGGERED
- reconciliation_status：MATCHED_BY_CLORDID / MATCHED_BY_ORDID / ADOPTED_LIVE_POSITION / UNMATCHED_LIVE_POSITION
- verifier status：approved / veto / missing_data_only
- macro_permission：ALLOW_BOTH / LONG_ONLY / SHORT_ONLY / NO_TRADE
- source：new / adopted / reconciled / unmatched_closed

### 翻译维护方式

- 短文案放在前端 i18n 字典。
- 后端长文本如果来自模型，需要同时保存原始文本和可选翻译文本；没有翻译文本时前端显示原文并标注来源。
- 新增页面或字段时，必须同时补中文和英文 key。
- CI 或构建脚本后续应增加缺失 key 检查，避免中文有、英文缺。

### 8.1 公开可展示

- 宏观状态
- 流动性趋势
- 模型方向输出
- Qlib 概率
- 历史订单聚合结果
- 收益曲线
- 赞赏地址

### 8.2 需要脱敏或隐藏

- DeepSeek 完整 prompt
- API keys
- Mongo URI
- OKX account id
- 交易所 raw response
- 精确账户现金，如要公开可做百分比化或延迟展示

### 8.3 实盘保护

前端 MVP 只读。任何执行控制按钮都不进入本期范围。

## 9. 阶段计划

### Phase 1: 只读中控台

- Dashboard
- Macro & Liquidity
- Decision Center
- Positions
- Orders
- Support

### Phase 2: 绩效分析

- 收益曲线 vs BTC
- 回撤
- 历史订单归因
- reason_code/trigger_source 表现分析

### Phase 3: 订单级回测

- 历史订单过滤
- 参数化回测
- 结果曲线
- 策略归因

### Phase 4: 行情级回测

- bar replay
- 手续费/滑点
- 同时持仓约束
- 按策略配置重算 entry/exit

## 10. 验收标准

### Dashboard

- 能看到当前持仓数量、账户收益、BTC 基准对比和最新决策摘要。
- 不在 Dashboard 展示系统状态；系统运行、Qlib 数据新鲜度、Qlib 模型是否最新统一放在 System Health。

### Macro

- 能看到当前宏观状态、流动性方向、边际变化。
- 能解释宏观对仓位和方向权限的影响。

### Decision Center

- 能追踪每个币从 marketState 到 modelDecision、trade_plan、riskReview、verifier、execution 的完整链路。
- 模型失败时能看到 fallback 原因。

### Positions

- 能看到所有当前持仓的盈亏、风险、失效条件和 runtime 动作。

### Orders

- 每个历史订单都能看到开仓理由、平仓理由和实际盈亏。

### Backtest

- 用户能按历史订单筛选条件运行回测。
- 返回收益、回撤、胜率、profit factor、订单列表和 BTC 对比曲线。

### Support

- 能展示 SOL 地址和支付宝二维码。
- SOL 地址可复制。
- 显示网络和风险提示。
