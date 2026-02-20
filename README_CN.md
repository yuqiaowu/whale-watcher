# 🐋 AI 鲸鱼监控与量化交易终端 (Dolores V2.0)

这是一个企业级、完全自主的加密货币 AI 量化交易与链上数据监控终端。它结合了 **链上巨鲸分析 (On-chain Whale Tracking)**、**技术指标 (Technical Indicators)**、**全球宏观情绪 (Macro & Sentiment)** 以及 **Agentic AI 决策模型 (基于 DeepSeek)**，能够在无人干预的情况下进行 24/7 的市场研判与真金白银交易。

本系统包含一个强大的 Python 后台调度引擎与一个具有极佳多维数据可视化的 React/Next.js Web3 前端仪表盘。

📺 **实时在线演示 (Live Demo):** [https://whale.sparkvalues.com/](https://whale.sparkvalues.com/)

---

## 🌟 核心突破与功能 (Key Features)

### 1. 全自动 AI 基金经理 (Agentic AI Trader)
不再是简单的死板网格或均线策略，系统的核心大脑（DeepSeek LLM）综合了当前市场的六维多模态情报（资金、图形、宏观、杠杆、仓位），并在执行交易后自动附带 **开单逻辑 (Rationale)** 与 **风控计划 (Exit Plan)**。
*   **支持 OKX V5 统一账户**: 全自动处理多空双向 (Long/Short) 合约交易、动态杠杆计算、实时未实现盈亏 (uPnL) 监控。
*   **自带 OCO 止盈止损**: 系统每次开仓都会向 OKX 发送 Conditional Trigger 订单，严格锁定最大回撤。
*   **历史自我反思**: AI 每次交易前会拉取过去的历史判断与盈亏表现，动态调整当下的风险偏好。

### 2. 六维全景感知 (Multi-Dimensional Perception)
大模型每 4 小时进行一次深度思考，输入的数据包含：
*   **🐋 链上资金流**: 追踪巨鲸的买卖金额、稳定币净流入/流出 (基于 Moralis & Solana Helius API)。
*   **📊 技术面特征工程**: 不向 AI 抛原始 K 线，而是通过内部清洗提取 RSI, ADX (趋势极值), MACD 以及 **星级评分 (Star Ratings)**（基于价格排位、成交量异常和 RSI 极值的 0~3 星级评估法，专门寻找顶部反转与底部吸筹）。
*   **💸 衍生品清算**: 监控多空爆仓强平数据，寻找空头轧空 (Short Squeeze) 机会。
*   **🌍 宏观经济 (Macro)**: 无缝集成美联储降息预期 (Fed Futures)、美元指数 (DXY)、美债收益率 (US10Y)、VIX 恐慌指数、日元套利影响 (Japan Rates) 以及全球恐慌贪婪指数。
*   **📰 新闻情绪面**: 实时抓取圈内头条新闻并分析整体文本情绪分。

### 3. 数据层与部署架构彻底解耦 (V2.0 更新)
*   **云原生 MongoDB 存储**: 彻底告别了依靠 GitHub commit 同步数据的痛点。现在系统的后台执行记录、组合净值 (Portfolio State) 与实时市场研判全都毫秒级保存至 MongoDB。
*   **Serverless 前端**: 前端基于 React/TypeScript 构建，部署于 Vercel。提供赛博朋克风的动态布局，具备多语言切换 (i18n)、实时资金收益曲线绘制、大模型多维分析报告展示等功能。
*   **自动化容器调度**: 后端通过 Railway 等云平台进行调度，严格匹配 4 小时 K 线收盘时间（0点, 4点, 8点...）执行感知-分析-交易的闭环运转。

### 4. 实时战报多渠道预警
*   集成 Telegram (HTML 渲染) 和 Discord 通知。只要模型触发了下单、平仓或检测到重大异动，实时代币方向、盈亏概览和 AI 判断的“核心理由”都会推送到手机。

---

## 🛠️ 技术栈与系统架构 (Tech Stack)

### **Backend (Python 3.10+)**
*   **`ai_trader.py`**: 基金经理大脑。构建复杂的 Prompt，通过 DeepSeek API 思考并调用执行器下单。
*   **`crypto_brain.py`**: 情报总局。负责拼接所有外部 API (Moralis/Macro/News) 的数据。
*   **`technical_analysis.py`**: Quant 引擎。负责计算 RSI、ADX、星级打分以及流动性指标。
*   **`okx_executor.py`**: 执行引擎。封装了高健壮性的 OKX V5 REST API 签名、下单和鉴权。
*   **`db_client.py`**: 数据持久化引擎。连接 MongoDB 处理状态。
*   **`run_loop.py`**: 时序调度器。对齐 K 线收盘时间启动工作流。

### **Frontend (React / Vite / Tailwind)**
*   组件化仪表盘：宏观流动性分析 (`detailed-stats`, `market-stats`)、巨鲸异动分析 (`whale-analytics`)、AI 跟单模拟 (`ai-copy-trading` 包含真实 PnL 曲线可视化)。

---

## 🚀 部署与运行指南

### 1. 核心环境变量 (`.env`)
无论在本地还是 Railway 部署，都需要配置以下核心秘钥：

```ini
# OKX 交易密钥
OKX_API_KEY="..."
OKX_SECRET_KEY="..."
OKX_PASSPHRASE="..."
TRADING_MODE="REAL" # 填 PAPER 可开启模拟盘不消耗真金白银

# 数据库与大语言模型
MONGODB_URI="mongodb+srv://..."
DEEPSEEK_API_KEY="sk-..."

# 数据源 API
MORALIS_API_KEYS="key1,key2" # 支持逗号分隔的密钥池轮换
SOLANA_API_KEYS="key1,key2"

# 消息通知
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="..."
```

### 2. 本地调试后端运行
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run_loop.py
```

### 3. Vercel 前端一键构建
```bash
cd frontend
npm install
npm run dev
# 或将其推送至 GitHub，Vercel 将自动识别 Vite 配置并完成发布
```

---

## 🛡️ 风险提示 (Disclaimer)
本项目作为一个完整的量化与链上监控体系，调用了真实的深度交易接口。尽管系统中内置了完备的异常处理、安全防线和硬止损逻辑，但加密货币市场的极端行情依然可能导致严重的资产折损。作者提供本架构仅作为学习与系统演示之目的，不对在 **REAL 模式实盘运行代码** 造成的资金亏损负责。建议先在纸面 (Paper Trading) 或模拟盘测试策略！
