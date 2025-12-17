# Web3 产品复盘：我如何用 AI 破解链上「聪明钱」的交易密码
## —— Whale Watcher 多链监控系统设计实录



## 1. 产品愿景与问题陈述 (Product Vision)
**痛点 (The Problem):** 散户交易者通常缺乏实时识别“聪明钱（Smart Money）”动向的工具。链上数据又充满了噪音，像 Etherscan 这样的原始交易列表对于缺乏专业知识的人来说晦涩难懂。
**解决方案 (The Solution):** Whale Watcher 是一个跨链分析引擎，通过检测、过滤链上的大规模资本流动（> $50k），生成实时的“市场情绪评分（Market Sentiment Score）”和 AI 驱动的市场叙事。

## 2. 技术架构 (展示“后端/API”能力)
作为一名兼具技术深度的产品经理，我将系统设计为轻量级、低成本且可扩展的架构。

```mermaid
graph TD
    A[外部数据源] -->|API 请求| B(后端聚合层 Python)
    subgraph Data_Sources [数据摄取]
        A1[Etherscan V2<br>(ETH 转账)]
        A2[Moralis<br>(SOL Swap/价格)]
        A3[Macro<br>(恐惧 greed 指数)]
    end
    A1 --> B
    A2 --> B
    A3 --> B

    subgraph Backend [分析引擎 Core]
        B --> C{信号分类逻辑}
        C -->|交易所流入| D[看空信号 (-)]
        C -->|交易所流出| E[看多信号 (+)]
        C -->|稳定币流向| F[购买力分析]
        C -->|闭环检测| G[剔除清洗交易]
        D & E & F & G --> H[原始情绪评分]
        H -->|EMA 平滑| I[最终情绪指数]
    end

    subgraph AI_Layer [AI 叙事层]
        I -->|JSON 数据| J[Google Gemini Agent]
        J -->|Prompt 工程| K[中英双语市场快报]
    end

    K --> L[前端展示 / 告警]
```

### 数据聚合层 (Data Aggregation)
-   **多源数据摄取:** 集成 **Etherscan V2 API**（用于获取细粒度的 ETH 转账事件）和 **Moralis API**（用于获取 Solana Swap 数据和实时代币定价）。
-   **宏观语境:** 引入外部宏观信号（如 BTC 恐惧与贪婪指数），对链上信号进行加权分析，避免孤立看数据。

### 分析引擎 (Analytical Engine - Python)
-   **信号逻辑 (Signal Logic):** 设计了一套自定义启发式算法来对交易进行分类：
    -   *交易所流入 (Exchange Inflow):* 潜在抛压 (Bearish)。
    -   *交易所流出 (Exchange Outflow):* 潜在吸筹 (Bullish)。
    -   *稳定币分析:* 追踪 USDT/USDC 的净流向，以检测系统内的“购买力（Buy Power）”变化。
    -   *闭环检测 (Loop Detection):* 过滤清洗交易（Wash Trading）和内部钱包互转，确保数据纯净。
-   **情绪平滑 (Sentiment Smoothing):** 对原始情绪评分应用 **指数移动平均 (EMA)** (Alpha=0.3)，以减少数据波动，为用户提供更稳定的趋势指标。

### AI 集成 (AI Integration)
-   **自动化分析师:** 集成 **Google Gemini** 来处理结构化的 JSON 数据（情绪评分、净流量、大额转账），并生成人类可读的中英双语“市场快报（Market Stories）”。这成功将冷冰冰的原始数据转化为可行动的决策依据。

### 基础设施策略
-   **类 Serverless CI/CD 流水线:** 利用 GitHub Actions/Scheduler 原则，每 4 小时运行一次分析。
-   **数据持久化:** 采用“Git-as-Database”方法，实现零成本、版本控制的市场状态历史记录。

---

## 3. 核心能力与职位要求对应 (Key Competencies Mapped to JD)

### 要求：“设计 Copy Trading / 后端服务” (职位 1, 职位 3)
-   **我的实践:** 设计了 *Whale Watcher* 后端来识别“可跟随钱包（Followable Wallets）”，通过追踪历史盈亏（基于价格拉升前的吸筹行为）来筛选。
-   **产品视角:** “我首先构建了追踪引擎。路线图的下一阶段是‘执行层（Action Layer）’——连接用户钱包，一键镜像这些‘高胜率’地址的操作。”

### 要求：“数据敏感度与分析能力” (职位 1, 职位 4)
-   **我的实践:** 我不只是展示交易列表，而是创造了一个衍生指标：**“情绪评分（Sentiment Score）”** (-2 到 +2)。
-   **指标设计:**
    -   稳定币流入 + 代币流出 = **看多 (+)**
    -   代币流入 + 稳定币流出 = **看空 (-)**
    -   基于交易金额的对数刻度（Logarithmic scale）加权，确保 $10M 的异动比 $50k 更重要，但又不会破坏评分标尺。

### 要求：“链的复杂性认知 (EVM, L2, Solana)” (职位 2, 职位 3)
-   **我的实践:** 该系统是 **全链适用（Chain-Agnostic）** 的。
    -   **Ethereum (EVM):** 追踪标准的 ERC-20 Transfer 事件。将 L2 桥（Optimism, Arbitrum, Hyperliquid）视为“交易所”，以捕捉跨链资本逃逸行为。
    -   **Solana (SVM):** 处理 Solana DEX 独特的“Swap”逻辑，识别 `sol_amount > threshold` 的转账。

### 要求：“竞品分析与策略” (职位 4)
-   **差异化:** 与 *Arkham*（对普通用户太复杂）或 *Dune*（太静态）不同，Whale Watcher 提供 **观点鲜明的信号（Opinionated Signals）**。它直接告诉用户 *怎么看*（看多/看空），而不仅仅是丢给他们一堆图表。

---

## 4. 产品路线图 (用于面试讨论)
这展示了您对产品 *未来* 的思考，而不仅仅是代码实现。

*   **阶段 1 (MVP - 已完成):** 核心监控、情绪评分、AI 叙事。
*   **阶段 2 (用户留存/Engagement):**
    *   **异动报警机器人:** Telegram/Discord 集成，针对 >$1M 的异动实时推送。
    *   **巨鲸排行榜:** 根据 PnL (盈亏) 对在此期间检测到的地址进行排名。
*   **阶段 3 (商业化/Monetization):**
    *   **跟单交易 (Copy Trading):** 针对头部巨鲸的“一键跟单”功能。
    *   **API 访问:** 将“清洗后的数据流”作为 API 服务出售给其他 dApp。

---

## 5. 面试模拟 Q&A

**Q: 你如何处理巨鲸追踪中的误报（False Positives）？**
*A: “我们在后端实现了‘闭环检测（Loop Detection）’算法。如果地址 A 转给 B，B 在同一个区块或小时内又转回给 A，这会被标记为‘内部闭环’并从情绪评分计算中剔除。这防止了清洗交易（Wash Trading）被误判为市场恐慌或 FOMO。”*

**Q: 为什么要区分 ETH 和 SOL 进行分析？**
*A: “因为它们代表了不同的市场心理。ETH 通常代表‘聪明钱’和机构（持有周期长），而 SOL 代表‘热钱’和散户（周转率高）。我的产品将它们分开分析，给用户提供更细腻的视角——可能出现‘既看多（ETH吸筹）又看空（SOL出货）’的背离情况，这本身就是一个强信号。”*

**Q: 你如何判断地址属于交易所？目前覆盖了哪些？**
*A: “为了保证 MVP 阶段数据的**高置信度**，我采用了**白名单机制 (Whitelist)**。我们维护了一个包含 **11 家主流 CEX**（如 Binance, OKX, Coinbase）和 **3 大跨链桥**（Optimism, Arbitrum, Hyperliquid）的核心热钱包数据库。相比于模糊匹配，这种硬编码方式能确保我们抓取的每一个‘流入/流出’信号都是实锤，绝无误判。”*

---

## 附录：算法逻辑详解 (Algorithm Deep Dive)
*这是展示您“数据敏感度”和“逻辑严密性”的核心部分。*

### 1. 信号定性规则 (Qualitative Scoring)
我们拒绝“黑盒”算法，而是采用了一套透明的启发式评分标准：

| 信号类型 | 分数 | 业务含义 | 底层逻辑 |
| :--- | :--- | :--- | :--- |
| **稳定币流入 (Exchange Inflow)** | **+2** | 强力买入 | 巨鲸充值 USDT 进场，意图抄底 (Buy Power)。 |
| **代币流出 (Token Outflow)** | **+1** | 温和持有 | 提币至冷钱包，减少市场流通盘，表明长期看好 (HODL)。 |
| **稳定币流出 (Exchange Outflow)** | **-1** | 获利离场 | USDT 提现离场，不再参与市场博弈。 |
| **代币流入 (Token Inflow)** | **-2** | 强力抛压 | 巨量 ETH/SOL 充值进交易所，砸盘意图明显 (Dump)。 |
| **内部闭环 (Internal Loop)** | **0** | 中性噪音 | 识别出地址 A -> B -> A 的行为，剔除无效数据。 |

### 2. 量化权重公式 (Quantitative Weighting)
为了防止单一巨额转账扭曲整体指标，同时又要体现大额资金的权重，我引入了 **对数加权 (Logarithmic Weighting)**：
> `Weight = log10(Transaction_Value_USD)`

*   **$10M 交易:** 权重 = 7.0
*   **$100k 交易:** 权重 = 5.0
*   **结果:** 千万级交易的影响力是十万级的 **1.4倍**，而非 100 倍。这符合市场中“边际效应递减”的规律，既尊重了大资金，又保护了指标及其稳定性。

### 3. 抗噪处理 (EMA Smoothing)
链上数据具有天然的脉冲性（Spiky）。为了给用户提供可参考的趋势，我在原始分数基础上叠加了 **EMA (指数移动平均)**：
> `Final_Score = (Current_Raw * 0.3) + (History_EMA * 0.7)`

这使得我们的 Sentiment Score 不会上蹿下跳，而是呈现出平滑的**趋势线**，有效过滤了单次的随机噪音。
