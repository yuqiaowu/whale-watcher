# 🐋 AI 鲸鱼监控与自动交易系统 (Dolores V1.4)

这是一个先进的、自主的加密货币交易系统，结合了 **链上鲸鱼分析**、**技术指标**、**全球宏观情绪** 以及 **强化学习风格的 AI 决策**。

Dolores (AI 代理) 24/7 全天候监控市场，识别异常情况（例如：散户恐慌抛售 vs 鲸鱼底部吸筹），并在 OKX 上执行交易（支持实盘或模拟盘），同时将所有分析数据同步到 Serverless 前端。

---

## 🌟 核心功能 (Key Features)

### 1. 六维感知 (Multi-Dimensional Perception)
AI 不仅仅看价格，她通过 6 个维度感知市场：
*   **🐋 链上资金流 (Flow)**: 追踪鲸鱼的代币净流入/流出和稳定币动向 (ETH & SOL)。
*   **📊 技术面 (Technicals)**: 高级指标包括 RSI, ADX (趋势强度), MACD, 以及 **布林带宽度/趋势 (BBW/Trend)**。
*   **⭐ 星级评分 (Star Ratings)**: 基于价格排位、成交量异常和 RSI 极值的自动评分系统 (0-3 星)。
*   **💸 市场痛点 (Pain)**: 监控 **爆仓数据 (Liquidation)** (多头 vs 空头谁在流血)，寻找反转和轧空机会。
*   **📉 资金费率 (Rates)**: 检测交易拥挤度和轧空潜力 (负费率 = 空头拥挤)。
*   **🌍 宏观环境 (Macro)**: 整合美联储利率期货、VIX 恐慌指数、美元指数 (DXY) 和全球新闻情绪。

### 2. "诚实且健壮" 的架构 (Honest & Robust)
*   **Fail-Loudly (主要报错)**: 系统在计算指标前会严格验证数据充足性 (>50 根 K 线)。如果关键数据 (如 ADX) 缺失，它会直接报错而不是使用虚假的默认值误导 AI。
*   **算术安全**: 在复杂的指标计算中增加了完善的除零保护。

### 3. AI 自我反思闭环 (V2.0 Alpha) 🧠
*   **滑动记忆 (Rolling Memory)**: AI 会维护一个包含最近 5 笔交易的“日记”，详细记录开仓时的市场快照 (RSI, ADX, 鲸鱼流向)。
*   **持续学习**: 在做任何新决策之前，AI 会先复盘这些历史记录，寻找成功或失败的模式（例如：“上次我在 ADX > 50 时抄底结果亏损了”）。这使得策略能够动态适应不断变化的市场风格。

### 4. Serverless 数据同步
*   **无需本地 Git**: 使用 GitHub REST API 直接推送数据到 `data-history` 分支。
*   **零维护成本**: 完美适配 Railway/Vercel 等无状态环境。

---

## 🛠️ 系统架构

*   **`backend/crypto_brain.py`**: **情报官**。负责抓取链上数据 (Moralis)、新闻和宏观数据。
*   **`backend/market_data.py`**: **矿工**。从 OKX 抓取 OHLCV 市场数据 (支持分页抓取 500 根 K 线)。
*   **`backend/technical_analysis.py`**: **分析师**。计算 RSI, ADX, 布林带, 星级评分等硬核指标。
*   **`backend/ai_trader.py`**: **基金经理**。汇总所有上下文信息，通过 DeepSeek LLM 进行最终交易决策。
*   **`backend/data_sync.py`**: **档案员**。将 JSON 数据上传到 GitHub `data-history` 分支。
*   **`backend/run_loop.py`**: **调度员**。每 4 小时唤醒一次系统。

---

## 🚀 部署指南 (Railway)

### 1. 环境变量配置
请在 Railway 项目设置中配置以下变量：

| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `OKX_API_KEY` | OKX API Key | `...` |
| `OKX_SECRET_KEY` | OKX Secret | `...` |
| `OKX_PASSPHRASE` | OKX Passphrase | `...` |
| `DEEPSEEK_API_KEY`| DeepSeek AI Key | `sk-...` |
| `MORALIS_API_KEY` | Moralis Key (链上数据) | `...` |
| `ETHERSCAN_API_KEY` | Etherscan Key | `...` |
| `GITHUB_TOKEN` | **数据同步必需**。需要 Repo 读写权限。 | `ghp_...` |
| `REPO_URL` | 您的 GitHub 仓库地址 | `github.com/yourname/whale-watcher` |
| `IS_PAPER_TRADING`| `true` 模拟盘, `false` 实盘 | `true` |

### 2. 前端集成
后端会自动将数据推送到 `data-history` 分支。您的前端应该直接读取 Raw URL：
```
https://raw.githubusercontent.com/username/repo/data-history/frontend/data/whale_analysis.json
```
这样不仅速度快，而且无需每次重新构建前端。

---

## 📊 数据结构 (whale_analysis.json)

生成的 JSON 文件包含：
*   **`eth`, `sol`, `btc`**: 各币种的独立板块。
    *   `market`: 实时价格、技术指标 (RSI, ADX, BBW, Funding)。
    *   `stats_24h`: 鲸鱼流向、爆仓数据。
    *   `history_60d`: 包含过去 60 个周期的历史数据数组（用于画图）。
*   **`ai_summary`**: AI 对当前市场状态的文字分析（中英文）。
*   **`actions`**: 执行的交易决策列表 (Open Long, Short 等)。

---

## 🛡️ 风险提示
这是一个实验性的 AI 代理系统。尽管它使用了复杂的逻辑和多维数据，加密货币市场仍然具有极高的波动性。建议在实盘前充分测试 (使用 Paper Trading 模式)。

---
*Built with ❤️ by Deepmind Advanced Coding Agent.*
