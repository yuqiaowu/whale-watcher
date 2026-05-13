import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Database,
  Gauge,
  GitBranch,
  HeartHandshake,
  Languages,
  LineChart,
  ListFilter,
  Radio,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  Wallet,
  XCircle,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLanguage } from "@/app/i18n/LanguageContext";
import type { Language } from "@/app/i18n/translations";

type PageId =
  | "dashboard"
  | "macro"
  | "decision"
  | "positions"
  | "orders"
  | "backtest"
  | "health"
  | "support";

type Tone = "green" | "yellow" | "red" | "blue" | "gray";

const pageIcons: Record<PageId, typeof Activity> = {
  dashboard: Gauge,
  macro: Radio,
  decision: BrainCircuit,
  positions: Wallet,
  orders: ListFilter,
  backtest: SlidersHorizontal,
  health: Database,
  support: HeartHandshake,
};

const navHistory = [
  { t: "05-04", nav: 10000, btc: 10000, excess: 0 },
  { t: "05-05", nav: 10084, btc: 9970, excess: 114 },
  { t: "05-06", nav: 10031, btc: 10040, excess: -9 },
  { t: "05-07", nav: 10142, btc: 10016, excess: 126 },
  { t: "05-08", nav: 10218, btc: 10104, excess: 114 },
  { t: "05-09", nav: 10176, btc: 10062, excess: 114 },
  { t: "05-10", nav: 10308, btc: 10110, excess: 198 },
  { t: "05-11", nav: 10396, btc: 10152, excess: 244 },
];

const liquidityHistory = [
  { t: "24h", stablecoin: -72 },
  { t: "20h", stablecoin: -54 },
  { t: "16h", stablecoin: -32 },
  { t: "12h", stablecoin: -18 },
  { t: "8h", stablecoin: -11 },
  { t: "4h", stablecoin: 9 },
  { t: "now", stablecoin: 21 },
];

const liquidityChartData = liquidityHistory.map((row) => ({
  ...row,
  stablecoinPositive: Math.max(row.stablecoin, 0),
  stablecoinNegative: Math.min(row.stablecoin, 0),
}));

const copy = {
  zh: {
    appTitle: "AI Crypto Terminal",
    appSubtitle: "交易中控台原型 / 基于 frontend_dashboard_prd.md",
    currentView: "当前视图",
    thesisRule: "模型只判断方向；仓位、杠杆、止损、止盈由程序控制。",
    languageLabel: "语言",
    status: {
      title: "系统状态",
      cycleFresh: "周期数据新鲜",
      cycleDetail: "最新决策周期 9 分钟前完成",
      qlibFresh: "Qlib 数据新鲜",
      qlibDetail: "特征数据已覆盖预期 4H bar",
      qlibModelFresh: "Qlib 模型为最新版本",
      qlibModelDetail: "当前模型 trained_at / data_latest_datetime 均在重训策略允许范围内",
    },
    pages: {
      dashboard: "总览",
      macro: "宏观与流动性",
      decision: "决策中心",
      positions: "持仓与执行",
      orders: "历史订单",
      backtest: "回测与复盘",
      health: "系统健康",
      support: "赞赏",
    },
    dashboard: {
      navTitle: "收益曲线 vs BTC 基准",
      legendNav: "策略净值",
      legendBtc: "BTC 买入持有基准",
      benchmarkNote: "两条线都按初始资金 10000 归一化，方便比较超额收益。",
      latestDecision: "最新决策摘要",
      systemStatus: "系统状态栏",
      macroState: "宏观边际状态",
      positionRisk: "当前持仓风险",
      metrics: [
        ["账户净值", "$10,396", "较初始资金 +3.96%", "green"],
        ["当前持仓", "2", "1 new / 1 adopted", "blue"],
        ["当日 PnL", "+$88.4", "已含未实现盈亏", "green"],
        ["最大回撤", "-2.7%", "最近 30 天", "yellow"],
      ] as Array<[string, string, string, Tone]>,
      macroExplanation: "仍偏防守，但 VIX 下行、stablecoin outflow 收窄，风险折扣减弱，不直接阻断模型交易意图。",
      systemRows: [
        ["决策周期", "cycle_2026-05-11_0800", "cycleId"],
        ["决策模式", "模型决策模式", "MODEL_DECISION_MODE"],
        ["交易模式", "模拟盘", "demo"],
        ["数据源", "whale_watcher_real", "Mongo target"],
      ] as Array<[string, string, string]>,
    },
    macro: {
      title: "当前宏观状态",
      trend: "流动性 24h 趋势",
      marginalTitle: "边际变化解释",
      marginal:
        "宏观仍为 risk-off，但压力比上一轮减弱：VIX 从 20.8 降到 17.8，stablecoin flow 从净流出转为小幅净流入。系统应降低风险折扣，而不是用宏观直接阻断模型交易意图。",
      legendStablecoin: "稳定币净流量",
      legendInflow: "净流入区间",
      legendOutflow: "净流出区间",
      legendZero: "0 线",
      unit: "单位：百万美元，正值代表净流入",
      metrics: [
        ["最终宏观判断", "轻度风险偏防守", "来源：LLM 最终裁决 / final_macro_decision", "yellow"],
        ["宏观影响分", "0.42", "较上一轮 -0.11 / macro_impact_score", "blue"],
        ["判断置信度", "72%", "加密市场相关性：高 / confidence", "green"],
        ["交易方向权限", "允许多空双向", "只影响仓位/杠杆，不删除模型交易意图 / macro_permission", "blue"],
      ] as Array<[string, string, string, Tone]>,
      flowMetrics: [
        ["稳定币净流量", "+$21M", "+$93M / 24h", "从净流出转为净流入，说明场内可用美元流动性在改善。", "green"],
        ["VIX", "17.8", "-3.0", "恐慌/波动率压力下降，risk-off 强度减弱。", "yellow"],
        ["资金费率 z-score", "+0.5", "正常", "资金费率接近中性偏多，暂未显示明显多头拥挤。", "blue"],
        ["代币净流量", "+$7M", "改善中", "代币净流向改善，但强度低于稳定币流动性变化。", "green"],
      ] as Array<[string, string, string, string, Tone]>,
      fields: {
        macroBiasTier: "宏观偏向等级",
        macroPermission: "交易方向权限",
        mildRiskOff: "轻度风险偏防守",
        allowBoth: "允许多空双向",
      },
    },
    decision: {
      listTitle: "Symbol 决策列表",
      detailTitle: "决策详情抽屉",
      tradePlans: "个交易计划",
      tabs: ["市场状态", "模型决策", "交易计划", "风控审核", "执行", "审计链路"],
      symbol: "Symbol",
      model: "Model",
      final: "Final",
      confidence: "置信度",
      planCount: "交易计划数",
      tradePlan: "model_trade_plan",
      adoption: "阻断 / 采纳说明",
      badges: ["模型直接给方向", "程序控制仓位", "verifier 二次审核"],
      modelLedNote: "最新版本不再由策略层先生成候选交易；模型输出 BUY / SELL / WAIT 和方向，程序再转换成 OPEN_LONG / OPEN_SHORT 并负责风控、失效条件白名单、杠杆仓位和执行。",
      tabBodies: [
        "展示价格、Qlib 概率、技术指标、宏观与链上覆盖情况。",
        "展示模型动作、方向、置信度、reason_codes 和 invalid_if。",
        "展示由 modelDecision 转换出的交易计划，包括方向、入场方式、止损止盈、最大持仓 bar 和失效条件。",
        "展示程序风控是否批准、仓位/杠杆折扣、verifier 是否否决或仅提示缺失数据。",
        "展示是否下单、clOrdId / ordId、成交状态和失败原因。",
        "展示 modelDecision、riskReview、verifier、execution、runtime review 的完整 provenance。",
      ],
      detailPanels: [
        {
          title: "市场状态输入",
          bullets: ["当前价、Qlib 8h 概率、技术指标和宏观权限会进入 modelDecision prompt。", "链上覆盖不足时展示为数据覆盖限制，不等同于硬否决。"],
          fields: [["当前价格", "$3,486.2", "blue"], ["Qlib p_up_8h", "0.64", "green"], ["宏观权限", "ALLOW_BOTH", "blue"]],
          sourceTitle: "真实后端字段",
          sources: ["record.marketState", "snapshot.decision_ready_features", "latest_decision_cycle_v2.qlib_freshness"],
        },
        {
          title: "模型方向结论",
          bullets: ["模型只输出 BUY / SELL / WAIT / HOLD 与 direction，不直接控制仓位。", "高置信方向单才进入 verifier 二次审核。"],
          fields: [["action / direction", "BUY / LONG", "green"], ["risk_level", "MEDIUM", "yellow"], ["model_role", "direction_only", "blue"]],
          sourceTitle: "真实后端字段",
          sources: ["record.modelDecision.action", "record.modelDecision.direction", "record.modelDecision.verifier"],
        },
        {
          title: "模型交易计划",
          bullets: ["后端字段仍叫 candidate_proposals，但 generation_mode=model_decision 时前端展示为交易计划。", "止损、止盈、最大持仓 bar 由程序结合 ATR、risk_level 和账户约束生成。"],
          fields: [["entry_type", "MARKET", "blue"], ["max_holding_bars", "2", "yellow"], ["generation_mode", "model_decision", "green"]],
          sourceTitle: "真实后端字段",
          sources: ["record.candidate.generation_mode", "record.candidate.candidate_proposals[0]", "riskReview.approved_candidate"],
        },
        {
          title: "风控审核",
          bullets: ["程序决定是否 approved、最终 final_intent、仓位大小、杠杆和最大持仓窗口。", "MEDIUM/LOW 会按最新规则降杠杆、降仓位、缩短持仓 bar。"],
          fields: [["approved", "true", "green"], ["leverage", "3x", "blue"], ["position_size", "$1,250", "green"]],
          sourceTitle: "真实后端字段",
          sources: ["record.riskReview.approved", "record.riskReview.leverage", "record.riskReview.approved_position_size_usd"],
        },
        {
          title: "执行请求",
          bullets: ["只有 riskReview.approved=true 才会创建 OPEN_LONG / OPEN_SHORT 执行请求。", "下单身份会写入 client_order_id、order_tag 和 order_provenance，方便后续追溯。"],
          fields: [["execution_action", "OPEN_LONG", "green"], ["order_status", "PENDING_SUBMIT", "yellow"], ["order_tag", "WWV2", "blue"]],
          sourceTitle: "真实后端字段",
          sources: ["record.execution.execution_action", "record.execution.client_order_id", "record.execution.order_provenance"],
        },
        {
          title: "审计链路",
          bullets: ["前端需要把模型、风控、verifier、执行、runtime review 串成一条链。", "如果 reconciliation 匹配不上原始开仓记录，才展示 ADOPTED_LIVE_POSITION。"],
          fields: [["provenance", "matched_open_order", "green"], ["runtime", "10m scan", "blue"], ["review", "profit first", "yellow"]],
          sourceTitle: "真实后端字段",
          sources: ["record.provenance", "execution.history[]", "position_runtime.MAX_HOLDING_REVIEW_*"],
        },
      ] as DecisionDetailPanel[],
    },
    positions: {
      table: "当前持仓表",
      runtimeFeed: "Runtime 动作流",
      thesis: "thesis / invalidation",
      entry: "entry",
      current: "current",
      stop: "stop",
      take: "take",
      size: "名义仓位",
      margin: "保证金",
      leverage: "leverage",
    },
    orders: {
      table: "历史订单表",
      filterBadge: "支持 symbol / side / macro / reason_codes 筛选",
      filters: ["Symbol", "Side", "Trigger", "Macro", "Date Range"],
      columns: ["decisionId", "symbol", "trigger_source", "open / close", "PnL", "close_reason"],
    },
    backtest: {
      params: "订单级回测参数",
      run: "运行订单级回测",
      result: "回测结果摘要",
      options: [
        "symbol: ETH, BTC, BNB",
        "side: long / short / both",
        "model confidence min: 0.60",
        "macro conflict: no trade",
        "include adopted positions: false",
        "trigger_source: Blueprint_E1 / A2",
      ],
    },
    health: {
      title: "系统健康",
      rows: [
        ["latest_system_run", "status=completed / latest_run_at=2026-05-11 08:02:41", "green"],
        ["latest_decision_cycle_v2", "cycleId=cycle_2026-05-11_0800 / decision_mode=model_decision", "green"],
        ["qlib_freshness.fresh", "true / expected_completed_bar=2026-05-11 00:00", "green"],
        ["qlib_freshness.model_is_fresh", "true / model_trained_at 与 train_end 在重训策略允许范围内", "green"],
        ["DeepSeek pipeline", "reasoner -> formatter -> verifier；verifier 只在高置信方向单触发", "green"],
        ["reconciliation", "clOrdId / ordId / 时间价格匹配；失败才 ADOPTED_LIVE_POSITION", "blue"],
        ["position_runtime", "约 10 分钟扫描；到期盈利先平，不盈利再 review", "blue"],
        ["execution mode", "由后端 OKX mode / execution_enabled 决定，前端只读", "yellow"],
      ] as Array<[string, string, Tone]>,
    },
    support: {
      sol: "SOL 赞赏地址",
      alipay: "支付宝赞赏",
      solQr: "SOL QR",
      alipayQr: "Alipay QR",
      note: "用于支持项目维护、数据源与模型调用成本。",
    },
    decisions: [
      ["BTC", "104,820.5", "Rank 2 / p_up 0.58", "WAIT / LONG bias", "61%", 0, "WAIT", "宏观仍偏防守，价格未回踩到结构触发区", "fresh"],
      ["ETH", "3,486.2", "Rank 1 / p_up 0.64", "BUY / LONG", "68%", 1, "APPROVED_LONG", "Qlib 向上概率通过，回踩结构成立，仓位被宏观折扣", "approved"],
      ["BNB", "692.4", "Rank 4 / p_down 0.33", "WAIT", "55%", 0, "BLOCKED", "E2 short 被 p_flat_gate 阻断，A2 未形成真实触发 K", "blocked"],
      ["SOL", "174.8", "Rank 3 / p_flat 0.47", "WAIT", "52%", 0, "WAIT", "震荡概率过高，程序不接受低 RRR 结构", "wait"],
      ["DOGE", "0.1086", "Rank 1 / p_down 0.862", "SELL / SHORT", "75%", 1, "APPROVED_SHORT", "Qlib 8h 下跌概率较高，MACD 与均线结构偏空，verifier 通过", "approved"],
    ] as DecisionTuple[],
    positionsData: [
      ["ETH-USDT", "LONG", "new", "3,421.0", "3,486.2", "$1,250", "$625", "2.0x", "+$47.6", "+3.8%", "3,336.4", "3,612.0", "回踩后重新站上 4H 结构，Qlib 方向与技术同向", "NOT_TRIGGERED"],
      ["BTC-USDT", "SHORT", "adopted", "105,620.0", "104,820.5", "$800", "$533", "1.5x", "+$9.1", "+1.1%", "106,340.0", "103,900.0", "旧仓位接管，等待 runtime thesis 复核", "THESIS_WEAKENED_TRIGGERED"],
    ] as PositionTuple[],
    ordersData: [
      ["tdr_1028", "ETH", "LONG", "Blueprint_E1", "05-10 16:00", "open", "+3.8%", "macro_conflict_size_reduced"],
      ["tdr_1025", "BNB", "SHORT", "Blueprint_A2", "05-09 08:00", "05-10 20:00", "-1.6%", "INVALIDATION_TRIGGERED"],
      ["tdr_1019", "SOL", "LONG", "Blueprint_F2", "05-07 04:00", "05-08 12:00", "+2.4%", "MAX_HOLDING_PROFIT_TAKE_TRIGGERED"],
      ["tdr_1013", "BTC", "WAIT", "ModelDecision", "05-06 08:00", "skipped", "0.0%", "LOW_RRR"],
    ] as OrderTuple[],
  },
  en: {
    appTitle: "AI Crypto Terminal",
    appSubtitle: "Trading dashboard prototype / Based on frontend_dashboard_prd.md",
    currentView: "Current View",
    thesisRule: "The model decides direction only; sizing, leverage, stop loss and take profit are controlled by rules.",
    languageLabel: "Language",
    status: {
      title: "System Status",
      cycleFresh: "Cycle data fresh",
      cycleDetail: "Latest decision cycle completed 9 minutes ago",
      qlibFresh: "Qlib data fresh",
      qlibDetail: "Feature data covers the expected 4H bar",
      qlibModelFresh: "Qlib model is current",
      qlibModelDetail: "trained_at and data_latest_datetime are within the retraining policy window",
    },
    pages: {
      dashboard: "Dashboard",
      macro: "Macro & Liquidity",
      decision: "Decision Center",
      positions: "Positions & Runtime",
      orders: "Orders",
      backtest: "Backtest Lab",
      health: "System Health",
      support: "Support",
    },
    dashboard: {
      navTitle: "Equity Curve vs BTC Benchmark",
      legendNav: "Strategy NAV",
      legendBtc: "BTC buy-and-hold benchmark",
      benchmarkNote: "Both lines are normalized to 10,000 initial capital so excess return is directly comparable.",
      latestDecision: "Latest Decision Summary",
      systemStatus: "System Status",
      macroState: "Macro Marginal State",
      positionRisk: "Open Position Risk",
      metrics: [
        ["Account NAV", "$10,396", "+3.96% vs initial capital", "green"],
        ["Open Positions", "2", "1 new / 1 adopted", "blue"],
        ["Daily PnL", "+$88.4", "Includes unrealized PnL", "green"],
        ["Max Drawdown", "-2.7%", "Last 30 days", "yellow"],
      ] as Array<[string, string, string, Tone]>,
      macroExplanation: "Still defensive, but VIX is falling and stablecoin outflow is narrowing. Risk haircut is lower and should not directly block model trade intent.",
      systemRows: [
        ["Decision Cycle", "cycle_2026-05-11_0800", "cycleId"],
        ["Decision Mode", "Model decision mode", "MODEL_DECISION_MODE"],
        ["Trading Mode", "Demo", "demo"],
        ["Data Source", "whale_watcher_real", "Mongo target"],
      ] as Array<[string, string, string]>,
    },
    macro: {
      title: "Current Macro State",
      trend: "24h Liquidity Trend",
      marginalTitle: "Marginal Change Explanation",
      marginal:
        "Macro remains risk-off, but pressure is weaker than the previous cycle: VIX fell from 20.8 to 17.8 and stablecoin flow moved from net outflow to slight inflow. The system should reduce risk haircut instead of using macro to block model trade intent.",
      legendStablecoin: "Stablecoin net flow",
      legendInflow: "Net inflow zone",
      legendOutflow: "Net outflow zone",
      legendZero: "Zero line",
      unit: "Unit: USD millions. Positive values mean net inflow.",
      metrics: [
        ["final_macro_decision", "MILD RISK-OFF", "source: llm_adjudicated", "yellow"],
        ["macro_impact_score", "0.42", "-0.11 vs previous cycle", "blue"],
        ["confidence", "72%", "crypto relevance: high", "green"],
        ["permission", "ALLOW_BOTH", "Affects size/leverage only, does not remove model trade intent", "blue"],
      ] as Array<[string, string, string, Tone]>,
      flowMetrics: [
        ["Stablecoin net flow", "+$21M", "+$93M / 24h", "Moved from net outflow to net inflow, improving available USD liquidity on exchanges.", "green"],
        ["VIX", "17.8", "-3.0", "Fear and volatility pressure declined, weakening the risk-off regime.", "yellow"],
        ["Funding z-score", "+0.5", "normal", "Funding is close to neutral and slightly positive, with no clear long crowding yet.", "blue"],
        ["Token net flow", "+$7M", "improving", "Token flow improved, but the move is weaker than the stablecoin liquidity change.", "green"],
      ] as Array<[string, string, string, string, Tone]>,
      fields: {
        macroBiasTier: "Macro Bias Tier",
        macroPermission: "Direction Permission",
        mildRiskOff: "Mild risk-off",
        allowBoth: "Allow both directions",
      },
    },
    decision: {
      listTitle: "Symbol Decision List",
      detailTitle: "Decision Detail Drawer",
      tradePlans: "trade plan(s)",
      tabs: ["Market State", "Model Decision", "Trade Plan", "Risk Review", "Execution", "Audit Trail"],
      symbol: "Symbol",
      model: "Model",
      final: "Final",
      confidence: "confidence",
      planCount: "trade plan count",
      tradePlan: "model_trade_plan",
      adoption: "Block / Adoption Explanation",
      badges: ["Model gives direction directly", "Rules control sizing", "Verifier second-pass review"],
      modelLedNote: "The latest version no longer relies on a strategy layer to generate candidates first. The model outputs BUY / SELL / WAIT plus direction; rules convert that into OPEN_LONG / OPEN_SHORT and handle risk, whitelisted invalidation conditions, leverage, sizing and execution.",
      tabBodies: [
        "Shows price, Qlib probabilities, technical indicators, macro state and on-chain data coverage.",
        "Shows model action, direction, confidence, reason_codes and invalid_if.",
        "Shows the trade plan converted from modelDecision, including direction, entry type, stop loss, take profit, max holding bars and invalidation conditions.",
        "Shows whether program risk approved it, size/leverage discounts, and whether verifier vetoed or only noted missing data.",
        "Shows order placement, clOrdId / ordId, fill status and failure reason.",
        "Shows the full provenance chain across modelDecision, riskReview, verifier, execution and runtime review.",
      ],
      detailPanels: [
        {
          title: "Market State Inputs",
          bullets: ["Current price, Qlib 8h probabilities, technical indicators and macro permission are sent into the modelDecision prompt.", "Missing optional on-chain coverage is shown as a coverage limitation, not a hard veto."],
          fields: [["Current Price", "$3,486.2", "blue"], ["Qlib p_up_8h", "0.64", "green"], ["Macro Permission", "ALLOW_BOTH", "blue"]],
          sourceTitle: "Real backend fields",
          sources: ["record.marketState", "snapshot.decision_ready_features", "latest_decision_cycle_v2.qlib_freshness"],
        },
        {
          title: "Model Direction Decision",
          bullets: ["The model outputs BUY / SELL / WAIT / HOLD plus direction; it does not control sizing.", "High-confidence directional decisions go through verifier review."],
          fields: [["action / direction", "BUY / LONG", "green"], ["risk_level", "MEDIUM", "yellow"], ["model_role", "direction_only", "blue"]],
          sourceTitle: "Real backend fields",
          sources: ["record.modelDecision.action", "record.modelDecision.direction", "record.modelDecision.verifier"],
        },
        {
          title: "Model Trade Plan",
          bullets: ["The backend field is still candidate_proposals, but generation_mode=model_decision should be shown as a trade plan.", "Stop loss, take profit and max holding bars are generated by rules using ATR, risk_level and account constraints."],
          fields: [["entry_type", "MARKET", "blue"], ["max_holding_bars", "2", "yellow"], ["generation_mode", "model_decision", "green"]],
          sourceTitle: "Real backend fields",
          sources: ["record.candidate.generation_mode", "record.candidate.candidate_proposals[0]", "riskReview.approved_candidate"],
        },
        {
          title: "Risk Review",
          bullets: ["Rules decide approved, final_intent, position size, leverage and the max holding window.", "MEDIUM/LOW tiers reduce leverage, reduce size and shorten the holding window."],
          fields: [["approved", "true", "green"], ["leverage", "3x", "blue"], ["position_size", "$1,250", "green"]],
          sourceTitle: "Real backend fields",
          sources: ["record.riskReview.approved", "record.riskReview.leverage", "record.riskReview.approved_position_size_usd"],
        },
        {
          title: "Execution Request",
          bullets: ["OPEN_LONG / OPEN_SHORT is created only when riskReview.approved=true.", "Order identity is written to client_order_id, order_tag and order_provenance for later reconciliation."],
          fields: [["execution_action", "OPEN_LONG", "green"], ["order_status", "PENDING_SUBMIT", "yellow"], ["order_tag", "WWV2", "blue"]],
          sourceTitle: "Real backend fields",
          sources: ["record.execution.execution_action", "record.execution.client_order_id", "record.execution.order_provenance"],
        },
        {
          title: "Audit Trail",
          bullets: ["The frontend should connect model, risk review, verifier, execution and runtime review into one readable chain.", "ADOPTED_LIVE_POSITION is shown only when reconciliation cannot match the original opening record."],
          fields: [["provenance", "matched_open_order", "green"], ["runtime", "10m scan", "blue"], ["review", "profit first", "yellow"]],
          sourceTitle: "Real backend fields",
          sources: ["record.provenance", "execution.history[]", "position_runtime.MAX_HOLDING_REVIEW_*"],
        },
      ] as DecisionDetailPanel[],
    },
    positions: {
      table: "Open Positions",
      runtimeFeed: "Runtime Action Feed",
      thesis: "thesis / invalidation",
      entry: "entry",
      current: "current",
      stop: "stop",
      take: "take",
      size: "Notional",
      margin: "Margin",
      leverage: "leverage",
    },
    orders: {
      table: "Historical Orders",
      filterBadge: "Supports symbol / side / macro / reason_codes filters",
      filters: ["Symbol", "Side", "Trigger", "Macro", "Date Range"],
      columns: ["decisionId", "symbol", "trigger_source", "open / close", "PnL", "close_reason"],
    },
    backtest: {
      params: "Order-Level Backtest Parameters",
      run: "Run Order-Level Backtest",
      result: "Backtest Result Summary",
      options: [
        "symbol: ETH, BTC, BNB",
        "side: long / short / both",
        "model confidence min: 0.60",
        "macro conflict: no trade",
        "include adopted positions: false",
        "trigger_source: Blueprint_E1 / A2",
      ],
    },
    health: {
      title: "System Health",
      rows: [
        ["latest_system_run", "status=completed / latest_run_at=2026-05-11 08:02:41", "green"],
        ["latest_decision_cycle_v2", "cycleId=cycle_2026-05-11_0800 / decision_mode=model_decision", "green"],
        ["qlib_freshness.fresh", "true / expected_completed_bar=2026-05-11 00:00", "green"],
        ["qlib_freshness.model_is_fresh", "true / model_trained_at and train_end are within retraining policy", "green"],
        ["DeepSeek pipeline", "reasoner -> formatter -> verifier; verifier runs only for high-confidence directional trades", "green"],
        ["reconciliation", "clOrdId / ordId / time-price matching; fallback is ADOPTED_LIVE_POSITION", "blue"],
        ["position_runtime", "Scans about every 10 minutes; expiry takes profit first, otherwise reviews thesis", "blue"],
        ["execution mode", "Controlled by backend OKX mode / execution_enabled; frontend is read-only", "yellow"],
      ] as Array<[string, string, Tone]>,
    },
    support: {
      sol: "SOL Support Address",
      alipay: "Alipay Support",
      solQr: "SOL QR",
      alipayQr: "Alipay QR",
      note: "Used to support project maintenance, data providers and model API costs.",
    },
    decisions: [
      ["BTC", "104,820.5", "Rank 2 / p_up 0.58", "WAIT / LONG bias", "61%", 0, "WAIT", "Macro remains defensive and price has not pulled back into the structural trigger zone.", "fresh"],
      ["ETH", "3,486.2", "Rank 1 / p_up 0.64", "BUY / LONG", "68%", 1, "APPROVED_LONG", "Qlib upside probability passed, pullback structure is valid, and size was discounted by macro risk.", "approved"],
      ["BNB", "692.4", "Rank 4 / p_down 0.33", "WAIT", "55%", 0, "BLOCKED", "E2 short was blocked by the p_flat gate; A2 did not form a real trigger candle.", "blocked"],
      ["SOL", "174.8", "Rank 3 / p_flat 0.47", "WAIT", "52%", 0, "WAIT", "Flat probability is too high, and rules reject the low-RRR structure.", "wait"],
      ["DOGE", "0.1086", "Rank 1 / p_down 0.862", "SELL / SHORT", "75%", 1, "APPROVED_SHORT", "Qlib shows high 8h downside probability, MACD and moving-average structure are bearish, and verifier approved it.", "approved"],
    ] as DecisionTuple[],
    positionsData: [
      ["ETH-USDT", "LONG", "new", "3,421.0", "3,486.2", "$1,250", "$625", "2.0x", "+$47.6", "+3.8%", "3,336.4", "3,612.0", "Price reclaimed the 4H structure after a pullback, with Qlib and technical direction aligned.", "NOT_TRIGGERED"],
      ["BTC-USDT", "SHORT", "adopted", "105,620.0", "104,820.5", "$800", "$533", "1.5x", "+$9.1", "+1.1%", "106,340.0", "103,900.0", "Legacy position adopted by the new system, awaiting runtime thesis review.", "THESIS_WEAKENED_TRIGGERED"],
    ] as PositionTuple[],
    ordersData: [
      ["tdr_1028", "ETH", "LONG", "Blueprint_E1", "05-10 16:00", "open", "+3.8%", "macro_conflict_size_reduced"],
      ["tdr_1025", "BNB", "SHORT", "Blueprint_A2", "05-09 08:00", "05-10 20:00", "-1.6%", "INVALIDATION_TRIGGERED"],
      ["tdr_1019", "SOL", "LONG", "Blueprint_F2", "05-07 04:00", "05-08 12:00", "+2.4%", "MAX_HOLDING_PROFIT_TAKE_TRIGGERED"],
      ["tdr_1013", "BTC", "WAIT", "ModelDecision", "05-06 08:00", "skipped", "0.0%", "LOW_RRR"],
    ] as OrderTuple[],
  },
};

type DecisionTuple = [string, string, string, string, string, number, string, string, string];
type PositionTuple = [string, string, string, string, string, string, string, string, string, string, string, string, string, string];
type OrderTuple = [string, string, string, string, string, string, string, string];
type DecisionDetailPanel = {
  title: string;
  bullets: string[];
  fields: Array<[string, string, Tone]>;
  sourceTitle: string;
  sources: string[];
};
type Copy = typeof copy.zh;

function toDecisions(rows: DecisionTuple[]) {
  return rows.map(([symbol, price, qlib, model, confidence, candidates, final, reason, health]) => ({
    symbol,
    price,
    qlib,
    model,
    confidence,
    candidates,
    final,
    reason,
    health,
  }));
}

function toPositions(rows: PositionTuple[]) {
  return rows.map(([symbol, side, source, entry, current, size, margin, leverage, pnl, pnlPct, stop, take, thesis, runtime]) => ({
    symbol,
    side,
    source,
    entry,
    current,
    size,
    margin,
    leverage,
    pnl,
    pnlPct,
    stop,
    take,
    thesis,
    runtime,
  }));
}

function toOrders(rows: OrderTuple[]) {
  return rows.map(([id, symbol, side, source, open, close, pnl, reason]) => ({
    id,
    symbol,
    side,
    source,
    open,
    close,
    pnl,
    reason,
  }));
}

function cls(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

function StatusPill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const toneClass = {
    green: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    yellow: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    red: "border-red-400/30 bg-red-400/10 text-red-300",
    blue: "border-sky-400/30 bg-sky-400/10 text-sky-300",
    gray: "border-slate-500/40 bg-slate-500/10 text-slate-300",
  }[tone];

  return <span className={cls("inline-flex items-center rounded border px-2 py-1 text-[11px] font-medium", toneClass)}>{children}</span>;
}

function Panel({
  title,
  icon: Icon,
  children,
  action,
  className,
}: {
  title: string;
  icon?: typeof Activity;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cls("self-start rounded-md border border-slate-700/70 bg-[#111820]", className)}>
      <div className="flex min-h-12 items-center justify-between border-b border-slate-700/70 px-4 py-3">
        <div className="flex items-center gap-2">
          {Icon ? <Icon className="h-4 w-4 text-sky-300" /> : null}
          <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function MetricCard({ label, value, sub, tone = "gray" }: { label: string; value: string; sub?: string; tone?: Tone }) {
  const valueColor = {
    gray: "text-slate-50",
    green: "text-emerald-300",
    red: "text-red-300",
    yellow: "text-amber-300",
    blue: "text-sky-300",
  }[tone];

  return (
    <div className="rounded-md border border-slate-700/70 bg-[#0b1118] p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={cls("mt-2 font-mono text-2xl font-semibold", valueColor)}>{value}</div>
      {sub ? <div className="mt-2 text-xs text-slate-500">{sub}</div> : null}
    </div>
  );
}

function FlowMetric({ row }: { row: [string, string, string, string, Tone] }) {
  const [label, value, delta, description, tone] = row;
  const toneClass = {
    green: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10",
    yellow: "text-amber-300 border-amber-400/30 bg-amber-400/10",
    blue: "text-sky-300 border-sky-400/30 bg-sky-400/10",
    red: "text-red-300 border-red-400/30 bg-red-400/10",
    gray: "text-slate-300 border-slate-500/40 bg-slate-500/10",
  }[tone];

  return (
    <div className="rounded-md border border-slate-700/70 bg-[#0b1118] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-400">{label}</div>
          <div className={cls("mt-2 font-mono text-xl font-semibold", toneClass.split(" ")[0])}>{value}</div>
        </div>
        <span className={cls("rounded border px-2 py-1 text-[11px] font-medium", toneClass)}>{delta}</span>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{description}</p>
    </div>
  );
}

function DashboardPage({ c }: { c: Copy }) {
  const decisions = toDecisions(c.decisions);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-4">
        {c.dashboard.metrics.map(([label, value, sub, tone]) => (
          <MetricCard key={label} label={label} value={value} sub={sub} tone={tone} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Panel title={c.dashboard.navTitle} icon={LineChart} action={<StatusPill tone="green">excess +2.44%</StatusPill>}>
          <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
            <span className="flex items-center gap-2"><span className="h-2 w-6 rounded bg-emerald-300" />{c.dashboard.legendNav}</span>
            <span className="flex items-center gap-2"><span className="h-2 w-6 rounded bg-blue-400" />{c.dashboard.legendBtc}</span>
            <span>{c.dashboard.benchmarkNote}</span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={navHistory}>
                <defs>
                  <linearGradient id="navFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#263241" vertical={false} />
                <XAxis dataKey="t" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} domain={[9900, 10450]} />
                <Tooltip
                  formatter={(value, name) => [value, name === "nav" ? c.dashboard.legendNav : c.dashboard.legendBtc]}
                  contentStyle={{ background: "#0b1118", border: "1px solid #334155", borderRadius: 6 }}
                />
                <Area type="monotone" dataKey="nav" stroke="#34d399" fill="url(#navFill)" strokeWidth={2.5} name={c.dashboard.legendNav} />
                <Line type="monotone" dataKey="btc" stroke="#60a5fa" strokeWidth={3} dot={false} name={c.dashboard.legendBtc} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title={c.dashboard.latestDecision} icon={BrainCircuit}>
          <div className="max-h-[330px] space-y-3 overflow-y-auto pr-1">
            {decisions.map((item) => (
              <div key={item.symbol} className="rounded-md border border-slate-700/60 bg-[#0b1118] p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-mono text-sm font-semibold text-slate-100">{item.symbol}</div>
                    <div className="mt-1 text-xs text-slate-400">{item.model}</div>
                  </div>
                  <StatusPill tone={item.health === "approved" ? "green" : item.health === "blocked" ? "red" : "gray"}>{item.final}</StatusPill>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-400">{item.reason}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4">
        <Panel title={c.dashboard.macroState} icon={Radio}>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">{c.macro.fields.macroBiasTier}<span className="ml-2 text-[11px] text-slate-600">macro_bias_tier</span></span>
              <StatusPill tone="yellow">{c.macro.fields.mildRiskOff}</StatusPill>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">{c.macro.fields.macroPermission}<span className="ml-2 text-[11px] text-slate-600">macro_permission</span></span>
              <StatusPill tone="blue">{c.macro.fields.allowBoth}</StatusPill>
            </div>
            <p className="text-sm leading-6 text-slate-300">{c.dashboard.macroExplanation}</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function MacroPage({ c }: { c: Copy }) {
  return (
    <div className="grid items-stretch gap-4 xl:grid-cols-[0.9fr_1.1fr]">
      <Panel title={c.macro.title} icon={Radio} className="h-full self-stretch">
        <div className="rounded-md border border-slate-700/60 bg-[#0b1118] p-4">
          <div className="mb-3 text-xs text-slate-400">{c.macro.marginalTitle}</div>
          <p className="text-sm leading-6 text-slate-300">{c.macro.marginal}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <StatusPill tone="blue">波动压力缓和</StatusPill>
            <StatusPill tone="blue">情绪压力缓和</StatusPill>
            <StatusPill tone="yellow">利率路径不确定</StatusPill>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {c.macro.metrics.map(([label, value, sub, tone]) => (
            <MetricCard key={label} label={label} value={value} sub={sub} tone={tone} />
          ))}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {c.macro.flowMetrics.map((row) => <FlowMetric key={row[0]} row={row} />)}
        </div>
      </Panel>

      <Panel title={c.macro.trend} icon={BarChart3} className="h-full self-stretch">
        <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="flex items-center gap-2"><span className="h-2 w-5 rounded bg-emerald-300" />{c.macro.legendInflow}</span>
          <span className="flex items-center gap-2"><span className="h-2 w-5 rounded bg-rose-400" />{c.macro.legendOutflow}</span>
          <span className="flex items-center gap-2"><span className="h-px w-5 bg-slate-200" />{c.macro.legendZero}</span>
          <span>{c.macro.unit}</span>
        </div>
        <div className="h-[560px] rounded-md border border-slate-700/70 bg-[#0b1118] p-3">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={liquidityChartData}>
              <defs>
                <linearGradient id="stablecoinPositiveFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#34d399" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#34d399" stopOpacity={0.03} />
                </linearGradient>
                <linearGradient id="stablecoinNegativeFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#fb7185" stopOpacity={0.04} />
                  <stop offset="95%" stopColor="#fb7185" stopOpacity={0.34} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#263241" vertical={false} />
              <XAxis dataKey="t" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} domain={[-80, 30]} />
              <Tooltip
                formatter={(value, name) => {
                  if (name === "stablecoinPositive") return [`+${value}M`, c.macro.legendInflow];
                  if (name === "stablecoinNegative") return [`${value}M`, c.macro.legendOutflow];
                  return [`${value}M`, c.macro.legendStablecoin];
                }}
                contentStyle={{ background: "#0b1118", border: "1px solid #334155", borderRadius: 6 }}
              />
              <ReferenceLine y={0} stroke="#e2e8f0" strokeDasharray="5 5" strokeWidth={1.4} />
              <Area type="monotone" dataKey="stablecoinPositive" baseValue={0} stroke="none" fill="url(#stablecoinPositiveFill)" />
              <Area type="monotone" dataKey="stablecoinNegative" baseValue={0} stroke="none" fill="url(#stablecoinNegativeFill)" />
              <Line type="monotone" dataKey="stablecoin" stroke="#67e8f9" strokeWidth={2.4} dot={{ r: 3, fill: "#0b1118", strokeWidth: 2 }} />
            </AreaChart>
          </ResponsiveContainer>
          </div>
      </Panel>
    </div>
  );
}

function getDecisionTabJson(activeTab: number, selected: ReturnType<typeof toDecisions>[number]) {
  const intent = selected.final.includes("LONG") ? "LONG" : selected.final.includes("SHORT") ? "SHORT" : "FLAT";
  const action = intent === "LONG" ? "BUY" : intent === "SHORT" ? "SELL" : "WAIT";
  const executionAction = intent === "LONG" ? "OPEN_LONG" : intent === "SHORT" ? "OPEN_SHORT" : "DO_NOTHING";
  const riskApproved = selected.health === "approved";

  if (activeTab === 0) {
    return {
      marketState: {
        symbol: selected.symbol,
        current_price: selected.price,
        qlib: {
          rank_and_probability: selected.qlib,
          data_fresh: true,
          model_is_fresh: true,
        },
        technical: {
          macd: "available",
          moving_averages: "available",
          rsi_williams_atr: "available",
        },
        macro: {
          macro_permission: "ALLOW_BOTH",
          macro_bias_tier: "MILD_RISK_OFF",
        },
        data_coverage: {
          optional_onchain_missing_is_warning: true,
        },
      },
    };
  }

  if (activeTab === 1) {
    return {
      modelDecision: {
        schema_version: "model_decision_v1",
        action,
        direction: intent,
        confidence: selected.confidence,
        model_role: "direction_only",
        reason_codes: ["QLIB_DIRECTIONAL_EDGE", "TECHNICAL_ALIGNMENT"],
        verifier: riskApproved ? { veto: false, missing_data: [], risk_notes: [] } : { veto: true, veto_reasons: ["risk_review_blocked"] },
      },
    };
  }

  if (activeTab === 2) {
    return {
      candidate: {
        generation_mode: "model_decision",
        product_label: "model_trade_plan",
        candidate_proposals: riskApproved ? [{
          strategy_family: "DIRECTIONAL",
          decision_intent: intent,
          trigger_source: "MODEL_DECISION",
          entry_type: "MARKET",
          invalidation_basis: "programmatic_stop_and_approved_model_rules",
        }] : [],
        model_decision_diagnostic: {
          action,
          direction: intent,
          reason: riskApproved ? "candidate_created_from_model_decision" : "model_requested_no_new_directional_trade",
        },
      },
    };
  }

  if (activeTab === 3) {
    return {
      riskReview: {
        approved: riskApproved,
        final_intent: intent,
        approved_position_size_usd: riskApproved ? 1250 : 0,
        leverage: riskApproved ? 3 : 1,
        max_holding_bars: riskApproved ? 2 : 0,
        execution_action: executionAction,
        review_note: riskApproved ? "approved model_decision trade plan with risk tier adjustment" : "risk review blocked execution",
      },
    };
  }

  if (activeTab === 4) {
    return {
      execution: {
        execution_action: executionAction,
        order_status: riskApproved ? "PENDING_SUBMIT" : "NOT_REQUESTED",
        client_order_id: riskApproved ? "WW2605110800ETHxxxx" : null,
        order_tag: riskApproved ? "WWV2" : null,
        order_provenance: riskApproved ? {
          cycleId: "cycle_2026-05-11_0800",
          symbol: selected.symbol,
          intent,
          execution_action: executionAction,
        } : null,
      },
    };
  }

  return {
    auditTrail: [
      "marketState built from snapshot",
      "modelDecision generated by DeepSeek reasoner/formatter",
      "verifier runs for high-confidence directional trade",
      "riskReview converts model plan into executable risk",
      "execution writes client_order_id/order_provenance",
      "position_runtime reviews invalidation and max holding",
    ],
  };
}

function DecisionPage({ c }: { c: Copy }) {
  const decisions = toDecisions(c.decisions);
  const [selectedSymbol, setSelectedSymbol] = useState(decisions[1].symbol);
  const [activeTab, setActiveTab] = useState(2);
  const selected = decisions.find((item) => item.symbol === selectedSymbol) ?? decisions[0];
  const detail = c.decision.detailPanels[activeTab] ?? c.decision.detailPanels[0];
  const tabJson = getDecisionTabJson(activeTab, selected);

  return (
    <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <Panel title={c.decision.listTitle} icon={BrainCircuit}>
        <div className="overflow-hidden rounded-md border border-slate-700/70">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-xs text-slate-400">
              <tr>
                <th className="px-3 py-3">{c.decision.symbol}</th>
                <th className="px-3 py-3">Qlib</th>
                <th className="px-3 py-3">{c.decision.model}</th>
                <th className="px-3 py-3">{c.decision.final}</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((item) => (
                <tr
                  key={item.symbol}
                  onClick={() => setSelectedSymbol(item.symbol)}
                  className={cls("cursor-pointer border-t border-slate-700/60", selected.symbol === item.symbol ? "bg-sky-400/10" : "bg-[#0b1118] hover:bg-slate-800/50")}
                >
                  <td className="px-3 py-3 font-mono text-slate-100">{item.symbol}<div className="text-xs text-slate-500">${item.price}</div></td>
                  <td className="px-3 py-3 text-slate-300">{item.qlib}</td>
                  <td className="px-3 py-3 text-slate-300">{item.model}<div className="text-xs text-slate-500">{c.decision.confidence} {item.confidence}</div></td>
                  <td className="px-3 py-3"><StatusPill tone={item.health === "approved" ? "green" : item.health === "blocked" ? "red" : "gray"}>{item.final}</StatusPill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title={`${selected.symbol} ${c.decision.detailTitle}`} icon={GitBranch} action={<StatusPill tone="blue">{selected.candidates} {c.decision.tradePlans}</StatusPill>}>
        <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
          {c.decision.tabs.map((tab, index) => (
            <button
              key={tab}
              onClick={() => setActiveTab(index)}
              className={cls("shrink-0 rounded border px-3 py-2 text-xs", activeTab === index ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-slate-700 bg-[#0b1118] text-slate-400 hover:text-slate-100")}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="rounded-md border border-slate-700/70 bg-[#0b1118] p-4">
          <div className="mb-4 rounded-md border border-sky-400/20 bg-sky-400/5 p-3">
            <div className="text-sm font-semibold text-sky-100">{detail.title}</div>
            <div className="mt-2 space-y-1">
              {detail.bullets.map((item) => (
                <p key={item} className="text-sm leading-6 text-slate-300">{item}</p>
              ))}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {detail.fields.map(([label, value, tone]) => (
              <MetricCard key={label} label={label} value={value} tone={tone} />
            ))}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-xs text-slate-400">{activeTab === 2 ? c.decision.tradePlan : detail.sourceTitle}</div>
              <pre className="overflow-auto rounded-md border border-slate-700/70 bg-slate-950 p-3 text-xs leading-5 text-slate-300">{JSON.stringify(tabJson, null, 2)}</pre>
            </div>
            <div>
              <div className="mb-2 text-xs text-slate-400">{detail.sourceTitle}</div>
              <p className="rounded-md border border-slate-700/70 bg-slate-950 p-3 text-sm leading-6 text-slate-300">{selected.reason}</p>
              <div className="mt-3 rounded-md border border-slate-700/70 bg-slate-950 p-3">
                <div className="text-xs text-slate-500">key paths</div>
                <div className="mt-2 space-y-1">
                  {detail.sources.map((item) => (
                    <div key={item} className="font-mono text-xs text-slate-300">{item}</div>
                  ))}
                </div>
              </div>
              {activeTab === 2 ? <p className="mt-3 rounded-md border border-slate-700/70 bg-slate-950 p-3 text-xs leading-5 text-slate-400">{c.decision.modelLedNote}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {c.decision.badges.map((badge, index) => <StatusPill key={badge} tone={index === 0 ? "green" : index === 1 ? "blue" : "yellow"}>{badge}</StatusPill>)}
              </div>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function PositionsPage({ c }: { c: Copy }) {
  const positions = toPositions(c.positionsData);

  return (
    <div className="space-y-4">
      <Panel title={c.positions.table} icon={Wallet}>
        <div className="grid gap-4 lg:grid-cols-2">
          {positions.map((pos) => (
            <div key={pos.symbol} className="rounded-md border border-slate-700/70 bg-[#0b1118] p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-mono text-lg font-semibold text-slate-100">{pos.symbol}</div>
                  <div className="mt-1 flex gap-2"><StatusPill tone={pos.side === "LONG" ? "green" : "red"}>{pos.side}</StatusPill><StatusPill tone="gray">{pos.source}</StatusPill></div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-lg text-emerald-300">{pos.pnl}</div>
                  <div className="text-xs text-slate-500">{pos.pnlPct}</div>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="text-slate-400">{c.positions.entry} <span className="float-right font-mono text-slate-100">{pos.entry}</span></div>
                <div className="text-slate-400">{c.positions.current} <span className="float-right font-mono text-slate-100">{pos.current}</span></div>
                <div className="text-red-300">{c.positions.stop} <span className="float-right font-mono">{pos.stop}</span></div>
                <div className="text-emerald-300">{c.positions.take} <span className="float-right font-mono">{pos.take}</span></div>
                <div className="text-slate-400">{c.positions.size} <span className="float-right font-mono text-slate-100">{pos.size}</span></div>
                <div className="text-slate-400">{c.positions.margin} <span className="float-right font-mono text-slate-100">{pos.margin}</span></div>
                <div className="text-slate-400">{c.positions.leverage} <span className="float-right font-mono text-slate-100">{pos.leverage}</span></div>
              </div>
              <div className="mt-4 rounded-md border border-slate-700/70 bg-slate-950 p-3">
                <div className="mb-1 text-xs text-slate-500">{c.positions.thesis}</div>
                <p className="text-sm leading-6 text-slate-300">{pos.thesis}</p>
                <div className="mt-3"><StatusPill tone={pos.runtime === "NOT_TRIGGERED" ? "green" : "yellow"}>{pos.runtime}</StatusPill></div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={c.positions.runtimeFeed} icon={Clock3}>
        <div className="grid gap-3 md:grid-cols-4">
          {["HOLD", "THESIS_WEAKENED_TRIGGERED", "REDUCE_25", "MAX_HOLDING_PROFIT_TAKE_TRIGGERED"].map((event, index) => (
            <div key={event} className="flex items-center gap-3 rounded-md border border-slate-700/70 bg-[#0b1118] p-3">
              <div className={cls("flex h-8 w-8 items-center justify-center rounded-full border", index < 2 ? "border-amber-400/40 text-amber-300" : "border-slate-600 text-slate-500")}>{index + 1}</div>
              <div className="text-xs font-medium text-slate-300">{event}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function OrdersPage({ c }: { c: Copy }) {
  const orders = toOrders(c.ordersData);

  return (
    <Panel title={c.orders.table} icon={ListFilter} action={<StatusPill tone="gray">{c.orders.filterBadge}</StatusPill>}>
      <div className="mb-4 grid gap-3 md:grid-cols-5">
        {c.orders.filters.map((filter) => (
          <button key={filter} className="flex items-center justify-between rounded-md border border-slate-700/70 bg-[#0b1118] px-3 py-2 text-sm text-slate-300">
            {filter}<ChevronRight className="h-4 w-4 text-slate-500" />
          </button>
        ))}
      </div>
      <div className="overflow-hidden rounded-md border border-slate-700/70">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900/80 text-xs text-slate-400">
            <tr>{c.orders.columns.map((column) => <th key={column} className="px-3 py-3">{column}</th>)}</tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id} className="border-t border-slate-700/60 bg-[#0b1118]">
                <td className="px-3 py-3 font-mono text-slate-100">{order.id}</td>
                <td className="px-3 py-3"><StatusPill tone={order.side === "LONG" ? "green" : order.side === "SHORT" ? "red" : "gray"}>{order.symbol} {order.side}</StatusPill></td>
                <td className="px-3 py-3 text-slate-300">{order.source}</td>
                <td className="px-3 py-3 text-slate-400">{order.open}<div>{order.close}</div></td>
                <td className={cls("px-3 py-3 font-mono", order.pnl.startsWith("+") ? "text-emerald-300" : order.pnl.startsWith("-") ? "text-red-300" : "text-slate-400")}>{order.pnl}</td>
                <td className="px-3 py-3 text-slate-300">{order.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function BacktestPage({ c }: { c: Copy }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
      <Panel title={c.backtest.params} icon={SlidersHorizontal}>
        <div className="space-y-3">
          {c.backtest.options.map((item) => (
            <div key={item} className="rounded-md border border-slate-700/70 bg-[#0b1118] p-3 text-sm text-slate-300">{item}</div>
          ))}
          <button className="mt-2 w-full rounded-md bg-sky-500 px-4 py-3 text-sm font-semibold text-slate-950">{c.backtest.run}</button>
        </div>
      </Panel>
      <Panel title={c.backtest.result} icon={Target}>
        <div className="grid gap-4 md:grid-cols-4">
          <MetricCard label="total return" value="+8.4%" tone="green" />
          <MetricCard label="max drawdown" value="-3.1%" tone="yellow" />
          <MetricCard label="win rate" value="58%" tone="green" />
          <MetricCard label="profit factor" value="1.42" tone="blue" />
        </div>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={navHistory}>
              <CartesianGrid stroke="#263241" vertical={false} />
              <XAxis dataKey="t" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip contentStyle={{ background: "#0b1118", border: "1px solid #334155", borderRadius: 6 }} />
              <Area dataKey="excess" stroke="#60a5fa" fill="#60a5fa22" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  );
}

function HealthPage({ c }: { c: Copy }) {
  return (
    <Panel title={c.health.title} icon={Database}>
      <div className="grid gap-3 md:grid-cols-2">
        {c.health.rows.map(([name, value, tone]) => (
          <div key={name} className="flex items-center justify-between gap-4 rounded-md border border-slate-700/70 bg-[#0b1118] p-3">
            <div>
              <div className="text-sm text-slate-300">{name}</div>
              <div className="mt-1 text-xs text-slate-500">{value}</div>
            </div>
            {tone === "green" ? <CheckCircle2 className="h-5 w-5 text-emerald-300" /> : tone === "yellow" ? <AlertTriangle className="h-5 w-5 text-amber-300" /> : <XCircle className="h-5 w-5 text-red-300" />}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SupportPage({ c }: { c: Copy }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title={c.support.sol} icon={CircleDollarSign}>
        <div className="rounded-md border border-slate-700/70 bg-[#0b1118] p-6">
          <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-md border border-slate-600 bg-slate-950 text-xs text-slate-500">{c.support.solQr}</div>
          <div className="mt-4 rounded-md border border-slate-700/70 bg-slate-950 p-3 font-mono text-xs text-slate-300">9qJ...prototype...SOL</div>
        </div>
      </Panel>
      <Panel title={c.support.alipay} icon={HeartHandshake}>
        <div className="rounded-md border border-slate-700/70 bg-[#0b1118] p-6">
          <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-md border border-slate-600 bg-slate-950 text-xs text-slate-500">{c.support.alipayQr}</div>
          <div className="mt-4 rounded-md border border-slate-700/70 bg-slate-950 p-3 text-sm text-slate-300">{c.support.note}</div>
        </div>
      </Panel>
    </div>
  );
}

function ActivePage({ page, c }: { page: PageId; c: Copy }) {
  if (page === "macro") return <MacroPage c={c} />;
  if (page === "decision") return <DecisionPage c={c} />;
  if (page === "positions") return <PositionsPage c={c} />;
  if (page === "orders") return <OrdersPage c={c} />;
  if (page === "backtest") return <BacktestPage c={c} />;
  if (page === "health") return <HealthPage c={c} />;
  if (page === "support") return <SupportPage c={c} />;
  return <DashboardPage c={c} />;
}

export function TradingControlPrototype() {
  const { language, setLanguage } = useLanguage();
  const c = copy[language];
  const [activePage, setActivePage] = useState<PageId>("dashboard");
  const pages = useMemo(
    () => (Object.keys(c.pages) as PageId[]).map((id) => ({ id, label: c.pages[id], icon: pageIcons[id] })),
    [c.pages]
  );

  return (
    <div className="min-h-screen bg-[#081018] text-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-700/70 bg-[#081018]/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] flex-col gap-3 px-4 py-4">
          <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md border border-sky-400/40 bg-sky-400/10">
                <Activity className="h-5 w-5 text-sky-300" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-slate-50">{c.appTitle}</h1>
                <p className="text-xs text-slate-400">{c.appSubtitle}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="ml-1 flex items-center overflow-hidden rounded-md border border-slate-700/70 bg-[#0b1118]">
                <div className="flex items-center gap-1 px-2 text-xs text-slate-400">
                  <Languages className="h-3.5 w-3.5" />
                  {c.languageLabel}
                </div>
                {(["zh", "en"] as Language[]).map((item) => (
                  <button
                    key={item}
                    onClick={() => setLanguage(item)}
                    className={cls(
                      "px-3 py-2 text-xs font-semibold transition",
                      language === item ? "bg-sky-400/15 text-sky-100" : "text-slate-500 hover:text-slate-100"
                    )}
                  >
                    {item === "zh" ? "中文" : "EN"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <nav className="flex gap-2 overflow-x-auto pb-1">
            {pages.map((page) => {
              const Icon = page.icon;
              const active = page.id === activePage;
              return (
                <button
                  key={page.id}
                  onClick={() => setActivePage(page.id)}
                  className={cls(
                    "flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm transition",
                    active ? "border-sky-400/50 bg-sky-400/15 text-sky-100" : "border-slate-700/70 bg-[#0b1118] text-slate-400 hover:border-slate-500 hover:text-slate-100"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {page.label}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-5">
        <ActivePage page={activePage} c={c} />
      </main>
    </div>
  );
}
