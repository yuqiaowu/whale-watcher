# 🐋 Whale Monitor AI (鲸鱼监控智能交易系统)

![Project Banner](assets/banner.png)

<div align="center">

[🇺🇸 English](README.md) | [🇨🇳 中文](README_CN.md) | [🇯🇵 日本語](README_JP.md)

</div>

> **基于 DeepSeek R1、链上数据和实时市场分析的全自动加密货币量化交易 Agent。**

---

## 📖 项目介绍

**Whale Monitor AI** 不仅仅是一个交易机器人，它是住在你服务器里的高级市场分析师。它结合了三层数据来做出高置信度的交易决策：

1.  **宏观层**: 监控美联储利率、流动性趋势和全球新闻情绪。
2.  **鲸鱼层**: 追踪以太坊和 Solana 链上的实时大额转账（鲸鱼警报）。
3.  **市场层**: 分析订单簿深度、爆仓热力图和价格行为。

每隔 4 小时（可配置），AI 会消化这些海量数据，“思考”当前的市场状态（牛/熊/震荡），并以机构级的风控标准在 **OKX** 上执行交易。

---

## ✨ 核心功能

*   **🧠 大模型决策**: 使用 `DeepSeek-V3/R1` 进行类人推理，识别市场陷阱（例如“轧空”或“鲸鱼出货”）。
*   **🛡️ 机构级风控**:
    *   **逐仓模式 (Isolated Margin)**: 保护账户余额，避免单点爆仓风险。
    *   **硬止盈止损 (Hard TP/SL)**: 下单自动附带策略委托。即使机器人掉线，您的资金也是安全的。
    *   **智能仓位**: 根据波动率和确信度动态调整头寸大小。
*   **🔗 多链监控**: 支持 ETH 和 SOL 鲸鱼追踪。
*   **📱 实时推送**: 向 **Telegram** 和 **Discord** 发送详细的分析报告。

---

## 🌟 最佳实践与实时演示 (Live Demo)

看看机器人的实际运行效果！我们维护了一个实时看板和一个全自动运行此代码的 Telegram 信号群。

### 📊 实时看板 (Web Dashboard)
**[👉 whale.sparkvalues.com](https://whale.sparkvalues.com)**
*可视化查看 AI 的实时分析结果和资产追踪。*

### 📢 Telegram 信号群
**[👉 加入群组](https://t.me/+u-P4xaw0ZptlOGZl)**
*24/7 接收自动交易信号和鲸鱼预警。*

<div align="center">
  <img src="assets/telegram_qr.jpg" width="200" alt="加入 Telegram" />
</div>

---

## 🚀 快速开始

### 前置要求
*   [Docker](https://www.docker.com/) & Docker Compose
*   OKX 账户 (拥有交易权限的 API Key)
*   DeepSeek API Key
*   Moralis / Etherscan API Key (用于链上数据)

### 1. 克隆与配置
```bash
git clone https://github.com/your-repo/whale-monitor-ai.git
cd whale-monitor-ai

# 创建数据目录
mkdir -p assets
# 您可以将 banner.png 和 payment_code.jpg 放入 assets/ 以进行自定义
```

### 2. 配置环境变量
复制模板并填写您的密钥：
```bash
cp .env.example .env
nano .env
```
**关键配置项**:
*   `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`: 您的交易凭证。
*   `TRADING_MODE`: 实盘设为 `REAL`，模拟盘设为 `DEMO`。建议先用 DEMO 测试！
*   `DEEPSEEK_API_KEY`: AI 的大脑。

### 3. 使用 Docker 运行
一条命令搞定所有：
```bash
docker-compose up -d --build
```
机器人将在后台启动。查看日志：
```bash
docker-compose logs -f
```

---

## 🛠️ 详细配置

| 变量名 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `TRADING_MODE` | `REAL` 或 `DEMO`. 请务必先在 DEMO 环境测试！ | `DEMO` |
| `MAX_LEVERAGE` | AI 允许使用的最大杠杆倍数。 | `3` |
| `TIMEFRAME` | 执行间隔 (如 4h, 1h)。在代码 `run_loop.py` 中配置。 | `4 hours` |

---

## ☕ 请我喝杯咖啡

如果这个机器人帮您赚到了钱，欢迎打赏支持后续开发！

<div align="center">
  <img src="assets/payment_code.jpg" width="200" alt="Alipay" style="margin-right: 20px;" />
  <img src="assets/sol_card.png" width="200" alt="Solana" />
  <p>支付宝 (Alipay) | Solana (SOL)</p>
  <code>3bdnJtKwN1jWPXQZfzKKFb62HZwAYGQiCShCbG5suBRm</code>
</div>

---

## ⚠️ 免责声明
加密货币交易风险极高。本软件按“原样”提供，不提供任何明示或暗示的保证。AI 的决策基于概率而非确定性。**请自行承担使用风险。**
