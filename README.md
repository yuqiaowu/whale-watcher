# 🐋 AI Whale Watcher & Auto-Trader (Dolores V1.4)

An advanced, autonomous crypto trading system that combines **On-Chain Whale Analysis**, **Technical Indicators**, **Global Macro Sentiment**, and **Reinforcement Learning-style AI Decision Making**.

Dolores (the AI Agent) monitors the market 24/7, identifies anomalies (e.g., retail capitulation vs. whale accumulation), and executes trades on OKX (or paper trading) while synchronizing all data to a serverless frontend backend.

---

## 🌟 Key Features

### 1. Multi-Dimensional Perception (六维感知)
The AI does not just look at price. It perceives the market through 6 dimensions:
*   **🐋 On-Chain Flow**: Tracks Whale Net Inflow/Outflow and Stablecoin movements (ETH & SOL).
*   **📊 Technicals**: Advanced indicators including RSI, ADX (Trend Strength), MACD, and **Bollinger Band Width/Trend**.
*   **⭐ Star Ratings**: Automated signal scoring (0-3 Stars) based on Price Rank, Volume Anomalies, and RSI extremes.
*   **💸 Market Pain**: Monitors **Liquidation Data** (Longs vs Shorts blown out) to find reversals.
*   **📉 Funding Rates**: Detects crowded trades and Short Squeeze potential (Negative Funding).
*   **🌍 Macro**: Integrates Fed Rates, VIX, DXY, and Global News Sentiment.

### 2. "Honest & Robust" Architecture
*   **Fail-Loudly**: The system strictly validates data sufficiency (>50 candles) before calculating indicators. If critical data (like ADX) is missing, it raises an error rather than using fake default values.
*   **Arithmetic Safety**: Protected against division-by-zero errors in complex calculations.

### 3. AI Self-Reflection Loop (V2.0 Alpha) 🧠
*   **Rolling Memory**: The AI maintains a "Journal" of its last 5 trades, including the exact market context (RSI, ADX, Whale Flow) at the moment of entry.
*   **Continuous Learning**: Before making any new decision, the AI reviews this journal to identify patterns of success or failure (e.g., "Last time I bought when ADX > 50, I lost money"). This allows the strategy to adapt dynamically to changing market regimes.

### 4. Serverless Data Sync
*   **No Git Required**: Uses GitHub REST API to push analysis results to a dedicated `data-history` branch.
*   **Zero-Maintenance**: Works perfectly in stateless container environments (Railway, Vercel).

---

## 🛠️ System Architecture

*   **`backend/crypto_brain.py`**: The Intelligence Officer. Fetches on-chain data (Moralis), News, and Macro data.
*   **`backend/market_data.py`**: The Miner. Fetches OHLCV market data (500 candles with pagination) from OKX. 
*   **`backend/technical_analysis.py`**: The Analyst. Computes RSI, ADX, Bollinger Bands, and Star Ratings.
*   **`backend/ai_trader.py`**: The Fund Manager. Aggregates all context and makes final trading decisions via DeepSeek LLM.
*   **`backend/data_sync.py`**: The Archivist. Uploads JSON data to GitHub `data-history` branch.
*   **`backend/run_loop.py`**: The Scheduler. Runs the cycle every 4 hours.

---

## 🚀 Deployment Guide (Railway)

### 1. Environment Variables
Set these in your Railway project settings:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `OKX_API_KEY` | OKX API Key | `...` |
| `OKX_SECRET_KEY` | OKX Secret | `...` |
| `OKX_PASSPHRASE` | OKX Passphrase | `...` |
| `DEEPSEEK_API_KEY`| DeepSeek AI Key | `sk-...` |
| `MORALIS_API_KEY` | Moralis Key (On-Chain) | `...` |
| `ETHERSCAN_API_KEY` | Etherscan Key | `...` |
| `GITHUB_TOKEN` | **Critical for Data Sync**. Repo scope required. | `ghp_...` |
| `REPO_URL` | Your GitHub Repo URL | `github.com/yourname/whale-watcher` |
| `IS_PAPER_TRADING`| `true` for Demo, `false` for Real Money | `true` |

### 2. Frontend Integration
The backend pushes data to the `data-history` branch. Your frontend should fetch raw data from:
```
https://raw.githubusercontent.com/username/repo/data-history/frontend/data/whale_analysis.json
```
This ensures your frontend always shows the latest analysis without needing a rebuild.

---

## 📊 Data Structure (whale_analysis.json)

The generated JSON contains:
*   **`eth`, `sol`, `btc`**: Individual asset sections.
    *   `market`: Real-time price, technicals (RSI, ADX, BBW, Funding).
    *   `stats_24h`: Whale flow, liquidation data.
    *   `history_60d`: Array of last 60 periods for charting.
*   **`ai_summary`**: The AI's written rationale for the current market state.
*   **`actions`**: List of executed trade decisions (Open Long, Short, etc.).

---

## 🛡️ Risk Disclosure
This is an experimental AI Agent. While it uses sophisticated logic, crypto markets are highly volatile. Use "Paper Trading" mode for testing.

---
*Built with ❤️ by Deepmind Advanced Coding Agent.*
