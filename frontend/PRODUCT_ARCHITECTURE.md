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
*   **AI 模型**: DeepSeek-V3 (API 调用), Qlib (本地 LightGBM 模型)
*   **数据源**: OKX API (行情), Etherscan (链上), CryptoCompare (新闻)
*   **部署**: Vercel (前端) + Railway/VPS (后端 Python 服务)
