# 🐋 Whale Monitor AI

![Project Banner](assets/banner.png)

<div align="center">

[🇺🇸 English](README.md) | [🇨🇳 中文](README_CN.md) | [🇯🇵 日本語](README_JP.md)

</div>

> **Autonomous Crypto Quant Agent powered by DeepSeek R1, On-Chain Data, and Real-Time Market Analysis.**

---

## 📖 Introduction

**Whale Monitor AI** is not just a trading bot; it's a sophisticated market analyst that lives on your server. It combines three layers of data to make high-conviction trading decisions:

1.  **Macro Layer**: Monitors Fed rates, liquidity trends, and global news sentiment.
2.  **Whale Layer**: Tracks real-time large transfers (Whale Alerts) on Ethereum & Solana chains.
3.  **Market Layer**: Analyzes Order Book depth, Liquidation Heatmaps, and Price Action.

Every 4 hours (configurable), the AI digests this massive dataset, "thinks" about the market regime (Bull/Bear/Crab), and executes trades on **OKX** with institutional-grade risk management.

---

## ✨ Key Features

*   **🧠 Large Model Decision**: Uses `DeepSeek-V3/R1` to perform human-like reasoning, detecting market traps (e.g., "Short Squeeze" or "Whale Distribution").
*   **🛡️ Institutional Risk Control**:
    *   **Isolated Margin**: Protects account balance from single-position failures.
    *   **Hard TP/SL**: Automatically attaches Algo Orders to every trade. Your funds are safe even if the bot goes offline.
    *   **Smart Sizing**: Dynamically adjusts position size based on volatility and conviction.
*   **🔗 Multi-Chain Monitoring**: Supports ETH and SOL whale tracking.
*   **📱 Real-Time Alerts**: Sends detailed analysis reports to **Telegram** & **Discord**.

---

## 🌟 Best Practices & Live Demo

See the bot in action! We maintain a live dashboard and a Telegram signal group running this exact code.

### 📊 Live Dashboard
**[👉 whale.sparkvalues.com](https://whale.sparkvalues.com)**
*Real-time AI analysis visualization and asset tracking.*

### 📢 Telegram Signal Group
**[👉 Join Group](https://t.me/+u-P4xaw0ZptlOGZl)**
*Receive automated trade signals and whale alerts 24/7.*

<div align="center">
  <img src="assets/telegram_qr.jpg" width="200" alt="Join Telegram" />
</div>

---

## 🚀 Quick Start

### Prerequisites
*   [Docker](https://www.docker.com/) & Docker Compose
*   An OKX Account (API Key with Trade permissions)
*   DeepSeek API Key
*   Moralis / Etherscan API Keys (for on-chain data)

### 1. Clone & Setup
```bash
git clone https://github.com/your-repo/whale-monitor-ai.git
cd whale-monitor-ai

# Create data directories
mkdir -p assets
# Put your banner.png and payment_code.jpg in assets/ if you want customization
```

### 2. Configure Environment
Copy the template and fill in your keys:
```bash
cp .env.example .env
nano .env
```
**Critical Configs**:
*   `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`: Your trading credentials.
*   `TRADING_MODE`: Set to `REAL` for real money, `DEMO` for paper trading.
*   `DEEPSEEK_API_KEY`: The brain of the operation.

### 3. Run with Docker
One command to rule them all:
```bash
docker-compose up -d --build
```
The bot will start in the background. You can view logs via:
```bash
docker-compose logs -f
```

---

## 🛠️ Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TRADING_MODE` | `REAL` or `DEMO`. Always test in DEMO first! | `DEMO` |
| `MAX_LEVERAGE` | Maximum leverage allowed for AI to use. | `3` |
| `TIMEFRAME` | Execution interval (e.g., 4h, 1h). Configured in code `run_loop.py`. | `4 hours` |

---

## ☕ Buy Me a Coffee

If this bot helps you make profit, feel free to support the development!

<div align="center">
  <img src="assets/payment_code.jpg" width="200" alt="Alipay" style="margin-right: 20px;" />
  <img src="assets/sol_card.png" width="200" alt="Solana" />
  <p>Alipay (支付宝) | Solana (SOL)</p>
  <code>3bdnJtKwN1jWPXQZfzKKFb62HZwAYGQiCShCbG5suBRm</code>
</div>

---

## ⚠️ Disclaimer
Cryptocurrency trading involves high risk. This software is provided "AS IS" without warranty of any kind. The AI's decisions are based on probability, not certainty. **Use at your own risk.**
