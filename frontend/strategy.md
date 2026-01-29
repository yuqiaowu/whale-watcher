

# 🧠 ETH / SOL 巨鲸情绪 → 可交易信号系统（完整方案 V1）

## 一、系统总览（你在做什么）

> **目标**：
> 把「巨鲸链上行为」转化为 **可验证、可过滤、可执行** 的交易信号。

**核心哲学**：

* Transfers = **意图**
* OI = **是否建仓**
* Volume = **是否执行**
* Funding = **是否拥挤**
* Price Reaction = **市场是否认可**

**不是预测价格，而是判断：
👉“现在是不是站在胜率更高的一侧”**

---

## 二、基础层（你已有 + 修复补丁）

### 1️⃣ 数据时间窗（不变，但明确用途）

| 时间窗 | 用途          |
| --- | ----------- |
| 7d  | 结构性偏向（趋势背景） |
| 24h | 短期情绪冲击（择时）  |

⚠️ 规则：

* **不允许只用 24h 做决策**
* 24h 必须服从 7d 的方向或极值

---

### 2️⃣ Transfer 情绪评分（你原方案 + 补丁）

#### 原 score_map（保留）：

| 类型                 | 分数 |
| ------------------ | -- |
| BULLISH_INFLOW     | +2 |
| BULLISH_OUTFLOW    | +1 |
| BEARISH_OUTFLOW    | -1 |
| BEARISH_INFLOW     | -2 |
| NEUTRAL / INTERNAL | 0  |

#### 加权（保留）：

```text
weight = log10(amount_usd)
```

#### ⚠️ 补丁 1：BEARISH_INFLOW 拆级

```text
if non_stablecoin_inflow:
    if volume_spike or OI_up:
        score = -2
    else:
        score = -1
```

👉 避免把「调仓 / 对冲 / 交割」当成砸盘。

---

### 3️⃣ 情绪解释（非线性）

你**不直接用数值方向**，而是分区：

| Sentiment   | 含义            |
| ----------- | ------------- |
| +1.2 ~ +2.0 | 强趋势确认         |
| +0.3 ~ +1.2 | 温和偏多          |
| -0.3 ~ +0.3 | 噪音区（No Trade） |
| -1.2 ~ -0.3 | 温和偏空          |
| -2.0 ~ -1.2 | 抛压释放区（准备反转）   |

⚠️ **-1.5 不是追空信号，而是“找止跌”的信号**

---

## 三、确认层（新加的，决定你赚不赚钱）

### 4️⃣ Open Interest（必选）

#### 指标：

* `ΔOI_24h`
* `ΔOI_6h`（用于加速度）

#### 解读矩阵（核心）：

| Transfer 情绪 | OI | 含义           |
| ----------- | -- | ------------ |
| Bearish     | ↑  | 新空头（真利空）     |
| Bearish     | ↓  | 平多 / 交割（弱利空） |
| Bullish     | ↑  | 新多头（真利多）     |
| Bullish     | ↓  | 去杠杆（常是底部）    |

👉 **OI 决定 Transfer 是否“有效”**

---

### 5️⃣ 成交量确认（Execution Filter）

#### 指标：

```text
volume_ratio = volume_now / volume_24h_avg
```

#### 规则：

* `volume_ratio < 1.2` → **不确认**
* `volume_ratio ≥ 1.5` → **确认**
* `volume_ratio ≥ 2.0` → **强确认**

⚠️ 没成交量的信号，**一律降权**

---

### 6️⃣ Funding Rate（拥挤度刹车）

#### 指标：

* Funding 当前值
* Funding Z-score（可选）

#### 规则（不是方向，是限制）：

| 情绪      | Funding | 动作   |
| ------- | ------- | ---- |
| Bullish | 极正      | 禁止追多 |
| Bearish | 极负      | 禁止追空 |
| 情绪反转    | 回归 0    | 放行   |

---

### 7️⃣ 价格反应强度（市场认可度）

#### 简化公式：

```text
reaction_score = |price_change| / |sentiment_change|
```

#### 解读：

* 高 reaction → 市场认可
* 低 reaction → 情绪被吸收（反向准备）

---

## 四、信号融合（你最终真正用的东西）

### 8️⃣ Signal Confidence Score（0–100）

```text
confidence =
    0.30 * Transfer Sentiment
  + 0.25 * OI Alignment
  + 0.20 * Volume Confirmation
  + 0.15 * Funding Safety
  + 0.10 * Price Reaction
```

> 不是精确数学，是**决策权重**

#### 阈值：

| 分数    | 动作       |
| ----- | -------- |
| ≥ 75  | 可执行主信号   |
| 60–75 | 小仓位 / 试探 |
| 40–60 | 观察       |
| < 40  | 不交易      |

---

## 五、最终交易规则（你可以直接照着写策略）

### 多头条件（示例）：

* sentiment_7d ≥ +0.3
* sentiment_24h 回升
* OI ↑
* volume_ratio ≥ 1.5
* funding 非极正
* confidence ≥ 75

### 空头条件（示例）：

* sentiment_7d ≤ -0.3
* sentiment_24h 下行
* OI ↑
* volume_ratio ≥ 1.5
* funding 非极负
* confidence ≥ 75

