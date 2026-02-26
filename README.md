<p align="center">
  <img src="assets/banner.png" alt="ai_crypto_agent_banner" width="800" />
</p>

<p align="center">
  <a href="README_CN.md"><img src="https://img.shields.io/badge/简体中文-red?style=for-the-badge" alt="简体中文" /></a>
  <a href="README.md"><img src="https://img.shields.io/badge/English-blue?style=for-the-badge" alt="English" /></a>
  <a href="README_JP.md"><img src="https://img.shields.io/badge/日本語-green?style=for-the-badge" alt="日本語" /></a>
</p>

# 🐋 AI Whale Monitor & Quant Trading Terminal (Dolores V2.0)

**This is an autonomous, ultra-low-cost AI trend quant trading and on-chain data monitoring terminal using <font color="red">free on-chain resources</font>. It operates on a 4H analysis timeframe and is capable of 24/7 market assessment and execution via OKX Real/Paper trade without human intervention.**

📺 **Live Demo:** [https://whale.sparkvalues.com/](https://whale.sparkvalues.com/)

# ⭐ Feature List

> ⚠️ **Disclaimer**: This project is for learning, discussion, and research purposes only and does not constitute any investment advice.

| Module | Implemented |
| :--- | :--- |
| **Whale Hub** | ✅ Real-time monitoring of large ETH/SOL on-chain movements<br>✅ Multi-dimensional data integration (DefiLlama, Moralis, Etherscan)<br>✅ 24h/7d Stablecoin & Token net flow analysis<br>✅ Precise identification of whale "Accumulation" and "Distribution" signals<br>✅ Dynamic tracking of global market cap and liquidity changes |
| **AI Trading System (Dolores)** | ✅ Automated 4H decisions based on DeepSeek-V3<br>✅ **Qlib Relative Strength Model**: Multi-coin scoring & Rank-based weight recommendations<br>✅ **Narrative vs Reality Check**: Identifying news-driven vs priced-in traps<br>✅ **Tactical Discipline (4D Rules)**: Anti-liquidation rush and mandatory funding trap defense<br>✅ Shadow Mode vs Real Trading / OCO Take Profit & Stop Loss |
| **Macro, Liquidity & On-chain** | ✅ **Z-Score Anomaly Detection**: Statistical monitoring of volume and funding rate extremes<br>✅ **Whale Flow**: Deep integration of 7d/24h $ETH/$SOL net flows<br>✅ **Wick Perception (Wick Ratio)**: Automatic identification of reversal signals like long shadows<br>✅ Fed Rate expectations, Yen Carry Trade risk, DXY/VIX/Fear & Greed integration |
| **Integration & Automation** | ✅ Millisecond cloud state sync via MongoDB & GitHub real-time data persistence<br>✅ Multi-platform real-time trade alerts via Telegram & Discord<br>✅ Fully decoupled architecture (React + Flask)<br>✅ Automated Run Loop aligned with K-line closures |

---

This system includes a Python backend scheduling engine and a React/Next.js Web3 frontend dashboard with excellent multi-dimensional data visualization.
![whale.sparkvalues.com](image.png)
Profit curve and trading rationale decided by AI models
![alt text](image-2.png)
![alt text](image-5.png)
![alt text](image-4.png)
4H interval Telegram alerts and trade notifications
![alt text](image-1.png)
4H interval Discord alerts and trade notifications
![alt text](image-6.png)

---

# 📅 Update History (Changelog)

| Date | Major Updates |
| :--- | :--- |
| **2026-02-26** | **V2.0 Upgrade**: Integrated Qlib Model, Z-Score detection, and enhanced risk control. Added Quantitative & Regime Safety panels, Live Qlib Bridge for real-time data, and comprehensive multi-language support (UI & Docs). |
| **2026-02-25** | **Localization**: Full dual-language support for frontend (News feed, AI Trading section). Updated support & donation mechanisms with Solana Blink. |
| **2026-02-24** | **Risk Control**: Injected dynamic risk limits into AI prompts to prevent OKX trade rejections. Added self-healing utilities for DB NAV history. |
| **2026-02-23** | **AI Agent Enhancements**: Separated agent memory from history to prevent hallucinations. Injected 7-day whale flow trends into prompts. Stabilized baseline & NAV history generation. |

---

# 🌟 Key Features

### 1. Agentic AI Trader
Not a simple grid or moving average strategy. The core brain (DeepSeek LLM) synthesizes six-dimensional multi-modal intelligence (Capital, Technicals, Macro, Leverage, Portfolio) and automatically attaches **Rationale** and an **Exit Plan** to every trade.
*   **OKX V5 Unified Account Support**: Handles long/short perpetuals, dynamic leverage calculation, and real-time uPnL monitoring.
*   **Built-in OCO Orders**: Automatically sends Take Profit and Stop Loss conditional triggers to OKX to lock in risk.
*   **Narrative Verification & Scenarios**: Forces AI to evaluate if news is "priced in" and choose from "Trend Following", "Mean Reversion", or "Whale Front-Run" scenarios.
*   <font color="red">**Historical Self-Reflection**</font>: AI retrieves past judgements and PnL performance before каждой trade to dynamically adjust risk appetite.

### 2. Multi-Dimensional Perception
The model performs deep thinking every 4 hours, ingesting:
*   **🐋 On-chain Flow**: Tracking whale trade volumes and net stablecoin/token flows (via Moralis & Solana Helius API).
*   **📊 Technical Feature Engineering**: Instead of raw K-lines, it uses cleaned indicators like RSI, ADX, MACD, and **Star Ratings** (a 0-3 star evaluation based on price percentile, volume anomalies, and RSI extremes).
*   **💸 Derivative Liquidations**: Monitoring long/short liquidation data to find Short Squeeze opportunities.
*   **🌍 Macroeconomics**: Seamless integration of Fed rate expectations (Fed Futures), DXY, US10Y, VIX, Yen Carry Trade impacts, and Fear & Greed index.
*   **📰 News Sentiment**: Real-time crawling of crypto headlines with sentiment scoring.

### 3. Advanced Risk Control & Tactical Discipline
Dolores follows a strict set of "Battlefield Rules" to handle crypto volatility:
*   **Anti-Liquidity Rush**: During lopsided liquidations (>3x ratio) or vertical price moves, AI treats liquidations as "fuel" rather than reversal signals, prohibiting immediate counter-trades until volatility subsides.
*   **Wick Selection (Wick Confirmation)**: Even with whale warnings, AI waits for reversal patterns like long wicks (Wick Ratio) and price breakouts before entry.
*   **Derivative Trap Check**: Monitors Funding Rates and Open Interest. If funding is extreme (>0.03% or <-0.01%), AI identifies it as "Crowded Trade" and pauses entries to avoid Squeezes.
*   **Core Position Management**:
    - **Dynamic Exposure**: Allocates long/short limits based on BTC SMA200 (e.g., 98% long limit in Bull, 40% in Bear).
    - **Volatility-Adjusted Leverage**: Syncs with Fear & Greed index. In extreme markets (<20 or >80), it triggers "Defense Mode," capping leverage at 2x.
    - **Hard Slot Constraint**: Limits to 3 active slots to ensure natural risk diversification and prevent over-leveraging on a single coin.

### 4. Data Layer & Deployment Decoupling (V2.0 Update)
*   **Cloud-Native MongoDB**: No more GitHub commit sync pain. Execution logs, portfolio state, and real-time market judgements are saved with millisecond latency to MongoDB.
*   **Serverless Frontend**: Built with React/TypeScript and deployed on Vercel. Features a cyberpunk dynamic layout, i18n support, real-time PnL charts, and AI analysis reports.
*   **Automated Container Scheduling**: Backend runs on platforms like Railway, strictly matched to 4H K-line closures (00:00, 04:00, 08:00...) for the perceive-analyze-trade loop.

### 5. Multi-Channel Real-time Alerts
*   Integrated Telegram (HTML rendering) and Discord notifications. Every trade decision, exit, or major anomaly is pushed to your mobile with entry direction, PnL overview, and AI rationale.

---

# 🛠️ Tech Stack & Architecture

### **Backend (Python 3.10+)**
*   **`ai_trader.py`**: The Fund Manager brain. Builds complex prompts for DeepSeek to analyze and call the executor.
*   **`crypto_brain.py`**: Intelligence Agency. Aggregates all external APIs (Moralis/Macro/News).
*   **`technical_analysis.py`**: Quant Engine. Calculates RSI, ADX, Star Ratings, and liquidity metrics.
*   **`okx_executor.py`**: Execution Engine. Wraps OKX V5 REST API for robust signing, ordering, and authentication.
*   **`db_client.py`**: Data Persistence. MongoDB status handler.
*   **`run_loop.py`**: Sequential Scheduler. Aligns workflow with K-line closures.

### **Frontend (React / Vite / Tailwind)**
*   Componentized Dashboard: Macro liquidity analysis (`detailed-stats`), Whale movements (`whale-analytics`), and AI Copy Trading simulation with real PnL visualization.

---

# 🚀 Quick Start & Deployment Guide

To ensure a smooth experience for newcomers, please follow these steps.

### 0. Prerequisites
1.  **Python 3.10+**: [Download](https://www.python.org/downloads/)
2.  **Node.js 18+**: [Download](https://nodejs.org/)
3.  **MongoDB**: We recommend a free [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) instance.

---

### 1. Configure Environment Variables (`.env`)
Create a file named `.env` in the `backend` directory with the following:

| Variable | Source | Description |
| :--- | :--- | :--- |
| `OKX_API_KEY` | [OKX API Page](https://www.okx.com/account/my-api) | Ensure "Trade" permission is enabled |
| `DEEPSEEK_API_KEY` | [DeepSeek Platform](https://platform.deepseek.com/) | Recommend topping up a small balance |
| `MONGODB_URI` | [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) | Conn string: `mongodb+srv://...` |
| `MORALIS_API_KEYS` | [Moralis Admin](https://admin.moralis.io/) | For whale flow monitoring |
| `SOLANA_API_KEYS` | [Helius](https://www.helius.dev/) | For Solana data scraping |

---

### 2. Start Backend Engine
```bash
cd backend
# 1. Create venv (Recommended)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install Dependencies (takes 2-3 mins)
pip install -r requirements.txt

# 3. Run Main Program
python run_loop.py
```

---

### 3. Start Frontend Dashboard
```bash
cd frontend
# 1. Install Dependencies
npm install

# 2. Start Dev Server
npm run dev
# Visit http://localhost:3000 to see the dashboard
```

---

### 4. Cloud Deployment (Railway & Vercel)
*   **Backend (Railway)**: Link this repo to Railway. It will auto-detect scripts. Add `.env` vars in Railway settings.
*   **Frontend (Vercel)**: Link the frontend directory to Vercel for auto-deployment.

---

# ☕️ Buy Me a Coffee

Thanks for the Star ⭐ and Follow! Updates come frequently.
Author's contact info is on the homepage. Feel free to reach out with any questions.
Check out my other projects! PRs and Issues are welcome.
Thanks for the support! If this project helps you, feel free to buy the author a milk tea~~ (Makes my day! 😊😊)
thank you~~~

| Alipay | Solana (SOL/USDC) |
| :---: | :---: |
| <img src="frontend/public/alipay_qr.png" width="200" /> | <img src="frontend/public/sol_qr.png" width="200" /> |
| `newjowu@gmail.com` | `2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY` |

### 🚀 Solana Blink (One-Click Payment)
If you are using a Blink-supported wallet (Phantom/Backpack), click below to donate directly:
[Solana Quick Donate](https://www.dial.to/?action=solana-action:https://action.solscan.io/api/donate?receiver=2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY)

---
*Thanks for your support! All donations will be used to cover server and DeepSeek API costs.*

# 🛡️ Disclaimer
As a complete quant and on-chain monitoring system, this project calls real deep-level trading APIs. While built with comprehensive error handling, security safeguards, and hard stop-loss logic, extreme market conditions in cryptocurrency can still lead to significant asset loss. The author provides this architecture for education and demonstration purposes only and is not responsible for any financial losses incurred while running the code in **REAL mode**. It is recommended to test strategies in Paper Trading mode first!
