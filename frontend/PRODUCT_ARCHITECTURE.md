# AI Crypto Terminal - 统一架构与产品文档

## 1. 产品愿景 (Product Vision)
本项目（AI Crypto Terminal）旨在打造一个**全能型 AI 加密资产管理终端**。通过整合自动交易、市场情绪分析、链上巨鲸监控以及深度技术指标，为用户提供一个上帝视角的加密市场仪表盘，并由 AI 代理（Agent）自动执行最优交易策略。

核心理念：**"Data Driven, AI Executed" (数据驱动，AI 执行)**。

## 2. 现状分析 (Current State)
目前我们拥有四个独立且功能强大的子项目，它们各自为政，存在数据孤岛和资源浪费：

| 项目代号 | 核心功能 | 优势 | 局限性 |
| :--- | :--- | :--- | :--- |
| **AI Crypto Agent** | 自动跟单与交易执行 | 完整的 Qlib 模型 + DeepSeek 决策闭环 | 缺乏实时的链上监控 |
| **Whale Watcher** | 链上巨鲸转账监控 | 实时性强，直接对接链上数据 | 仅提供报警，未联动交易 |
| **News Analyse** | 新闻情绪量化分析 | 专注于舆情对价格的影响 | 数据未反哺给交易决策 |
| **Crypto Signal Lab** | 深度技术/链上指标 | 提供了 ATR、清算热图等深度数据 | 主要是离线分析脚本 |

## 3. 统一架构设计 (Unified Architecture)

我们将构建一个 **"Crypto Brain" (加密大脑)** 统一后端体系，采用微服务模块化设计，通过统一 API 网关服务于前端。

### 3.1 系统架构图

```mermaid
graph TD
    User([用户 / 浏览器]) --> |HTTPS| Frontend[React 前端仪表盘]
    
    subgraph "Unified Backend System (Python/Flask)"
        API_Gateway[API 网关 (Server.py)]
        
        subgraph "Layer 1: Perception (感知层)"
            Market_Svc[行情服务 (OKX/Binance)]
            News_Svc[舆情分析服务 (News Analyse)]
            OnChain_Svc[链上/巨鲸监控服务 (Whale Watcher)]
            Signal_Svc[技术指标计算 (Crypto Signal Lab)]
        end
        
        subgraph "Layer 2: Cognition (认知层)"
            Feature_Engine[Qlib 特征工程]
            Risk_Engine[风险控制引擎]
            Decision_Brain[DeepSeek AI 决策大脑]
        end
        
        subgraph "Layer 3: Execution (执行层)"
            Trade_Executor[模拟/实盘交易执行器]
            Logger[全链路日志记录]
        end
        
        DB[(统一数据存储\nJSON/CSV/SQLite)]
    end
    
    Frontend <--> API_Gateway
    API_Gateway <--> DB
    
    Layer_1 --> DB
    DB --> Layer_2
    Layer_2 --> DB
    DB --> Layer_3
```

### 3.2 模块集成方案

#### A. 核心交易引擎 (Core Engine)
*   **来源**: `external_backend` (AI Crypto Agent)
*   **角色**: 作为主系统的骨架。保留其 `run_daily_cycle.py` 作为主心跳，负责调度各个模块。
*   **职责**: 维护账户状态 (`portfolio_state.json`)，进行最终的买卖操作。

#### A1. Candidate / Rule Contract
*   **Candidate Layer** 只负责输出可审计候选，不负责最终批准开仓。
*   结构型候选必须携带 `reference_values` 与 `invalidation_conditions`。例如 `Blueprint_A2` 的上影线反抽空单必须优先使用真实已完成 4H K 线高点 `trigger_candle_high`，而不是用 `price + ATR` 合成高点。
*   Qlib 依赖候选必须携带 `qlib_freshness`。系统按最近已完成 4H bar 检查 Qlib payload 与特征 CSV，同时检查 `model_train_end / model_is_fresh`；若数据或模型过期，`Blueprint_E1` / `Blueprint_E2` / `Blueprint_G1` / `ModelDecision_LLM` 必须返回 `QLIB_STALE`，不得开仓或启动网格。
*   **Rule Engine** 批准开仓前必须按顺序执行：
    1. `QLIB_FRESHNESS_CHECK`：Qlib 过期时返回 `QLIB_STALE`；
    2. schema 校验；
    3. `PRE_TRADE_INVALIDATION_CHECK`：若当前价已经触发 `invalidation_conditions`，返回 `INVALIDATION_TRIGGERED`，不得开仓；
    4. `MIN_RRR_CHECK`：使用候选最终 `entry / SL / TP` 计算 RRR，低于阈值返回 `LOW_RRR`，不得开仓；
    5. 仓位冲突、宏观权限、强平距离与风险预算检查。
*   这保证模型、研究层与执行层看到的是同一套结构依据：A2 若因真实上影线顶部被突破而失效，不能继续作为可执行 candidate；若真实结构止损导致 RRR 不达标，也不能开仓。

#### A2. Model Decision Layer
*   默认仍走旧 candidate 蓝本。只有 `MODEL_DECISION_MODE=1` 时，才进入模型决策路径，并使用 `ModelDecision_LLM` 作为候选来源。
*   模型决策只负责方向判断，合法输出限定为 `BUY` / `SELL` / `HOLD` / `WAIT`、`LONG` / `SHORT` / `FLAT`、置信度、风险等级、理由和失效条件。仓位、杠杆、止损、止盈和执行动作仍由程序控制。
*   模型输入统一为 `marketState`，包含技术指标、Qlib、链上、宏观、持仓状态与 `data_availability`。`williams_r14` 和 `drawdown_120d_pct` 可为空，但必须显式标记数据是否可用。
*   模型链路仅使用 DeepSeek：`deepseek-reasoner` 先按 self-criticism 检查多空、空仓、缺失数据、失效条件与冲突，再由 `deepseek-chat` 输出结构化 JSON；`ENABLE_MODEL_DECISION_VERIFIER=1` 时可再由 verifier 复核高置信方向单。
*   模型可以输出 `invalidation_rules[]` 程序规则草案；程序只采纳字段、操作符和方向均通过白名单审核的规则，审核通过后写入 `candidate.invalidation_conditions`，审核失败写入 `model_rejected_invalidation_rules`。
*   任何模型未启用、接口失败、JSON 无效、方向不一致或 verifier 否决，都会保守降级为 `WAIT` / `FLAT`，不会误下单。
*   持久化字段包括 `qlib_freshness`、`marketState`、`modelDecision`，用于前端解释、审计和回放。

#### B. 情报中心 (Intelligence Center)
*   **来源**: `news_analyse` + `crypto_signal_lab`
*   **集成方式**:
    1.  抽取 `news_analyse` 的新闻抓取与 LLM 打分逻辑，作为 `fetch_news_module`。
    2.  抽取 `crypto_signal_lab` 的 ATR 波动率计算和清算数据逻辑，作为 `fetch_metrics_module`。
*   **价值**: 为 AI 提供除了“价格”以外的多维度输入（情绪 + 链上筹码分布）。

#### C. 监控雷达 (Monitor Radar)
*   **来源**: `whale_watcher`
*   **集成方式**: 作为一个独立的 Daemon (守护进程) 运行，不阻塞主交易循环。
*   **输出**: 将检测到的巨鲸异动实时写入 `whale_alerts.json`，供前端“消息流”组件读取展示。

## 4. API 接口规范 (API Specification)

为了支持前端 `src/app/components` 的无缝展示，后端将暴露以下标准化 RESTful 接口：

| HTTP 方法 | 路径 | 来源模块 | 描述 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/summary` | Core | 获取总资产、ROI、运行时间 |
| `GET` | `/api/positions` | Core | 获取当前持仓列表 (CryptoCard 组件用) |
| `GET` | `/api/history` | Core | 获取历史交易记录 |
| `GET` | `/api/nav-history` | Core | 获取净值曲线数据 (ProfitCurve 组件用) |
| `GET` | `/api/agent-decision` | AI Brain | 获取最新的 AI 决策逻辑文本 |
| `GET` | `/api/market-stats` | Intelligence | 获取宏观指标 (DXY, VIX, Fear&Greed) |
| `GET` | `/api/whale-alerts` | Monitor | **[新增]** 获取最近 24h 巨鲸异动 |
| `GET` | `/api/news-sentiment` | Intelligence | **[新增]** 获取新闻情绪聚合评分 |

## 5. 新前端功能规划 (Frontend Roadmap)

基于新的后端能力，前端将升级以下功能：

1.  **AI 决策透明化 (AI Copy Trading)**:
    *   直接展示后端 `agent_decision_log.json` 返回的自然语言逻辑（"为什么买 SOL？"）。
2.  **即时情报流 (Live Feed)**:
    *   新增一个 Sidebar 或悬浮窗，轮询 `/api/whale-alerts`，实时弹出巨鲸大额转账提醒。
3.  **多维图表**:
    *   在 K 线图上叠加 `news_analyse` 的情绪红绿点，直观展示新闻对价格的影响。

## 6. 技术栈 (Tech Stack)

*   **前端**: React 19, Vite, TailwindCSS, Motion (现有)
*   **后端**: Python 3.10+, Flask
*   **AI 模型**: DeepSeek reasoner/chat (API 调用), Qlib (本地 LightGBM 模型)
*   **数据源**: OKX API (行情), Etherscan (链上), CryptoCompare (新闻)
*   **部署**: Vercel (前端) + Railway/VPS (后端 Python 服务)
