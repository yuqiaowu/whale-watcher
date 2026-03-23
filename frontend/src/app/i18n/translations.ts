export const translations = {
  zh: {
    // Header
    title: 'AI 鲸鱼监控与量化交易V2.0',
    subtitle: 'WHALE MONITOR & QUANTITATIVE TRADING V2.0',
    language: '语言',

    // Navigation
    nav: {
      liquidity: '流动性情绪数据分析',
      aiCopyTrading: 'AI跟单',
      buyMeTea: '请我喝茶'
    },

    header: {
      liquidity: '流动性',
      volume: '成交量',
      marketCap: '市值'
    },

    // Market Analysis
    marketAnalysis: {
      title: 'AI 数据分析观点',
      updateTime: '更新状态',
      content: '🔄 正在等待 Dolores 的最新市场研判数据，请稍后刷新 (Awaiting live data...)',
      riskOn: '风险偏好',
      expand: '展开全文',
      collapse: '收起'
    },

    // Sections
    sections: {
      liquidityMarket: '流动性情绪数据分析',
      whaleAnalytics: '巨鲸数据分析',
      marketStats: '市场统计',
      cryptoSentiment: '加密货币情绪'
    },

    // AI Copy Trading
    aiTrading: {
      accountStats: '账户总值',
      initialValue: '初始金额',
      currentValue: '当前总值',
      todayChange: '今日',
      strategyDesc: '4小时线为基准的AI量化策略，已成功运行',
      runningTimePlaceholder: '-- 天 -- 小时',
      tabs: {
        current: '当前持仓',
        history: '历史记录',
        decisions: '模型决策'
      },
      positionProfitLoss: '持仓盈亏',
      remainingFunds: '剩余资金',
      holding: '持仓',
      openPrice: '开仓价',
      currentPrice: '当前价',
      stopLoss: '止损价',
      takeProfit: '止盈价',
      profitLoss: '盈亏',
      longMultiple: '做多',
      shortMultiple: '做空',
      // History tab
      historyStats: {
        totalProfitLoss: '总盈亏',
        winRate: '胜率',
        tradeCount: '交易次数'
      },
      long: '做多',
      short: '做空',
      closePrice: '平仓',
      quantity: '数量',
      leverage: '杠杆',
      // Decisions tab
      updateTime: '最新',
      marketAnalysis: '市场分析',
      actions: '执行动作',
      hold: 'HOLD',
      rejected: '已预警 (REJECTED)',
      marketLogic: '市场逻辑',
      riskWarning: '风险警告 (Rejection Reason)',
      position: '仓位',
      profitCurve: '收益曲线',
      cashBalance: '现金余额',
      noPositions: '暂无持仓',
      noHistory: '暂无历史交易记录',
      decisionDetail: '决策依据详情',
      logicLabel: '逻辑',
      entryLabel: '开仓',
      exitLabel: '平仓',
      btcBenchmark: 'BTC 基准',
      confidence: '模型置信度',
      technicalSignal: '技术信号 (Technical)',
      macroOnChain: '宏观与链上 (Macro/On-Chain)',
      quantitative: '量化指标 (Quantitative)',
      regimeSafety: '环境安全性 (Regime Safety)',
      portfolioStatus: '个人账户状态 (Portfolio Status)',
      redTeamAudit: '红色突击队审计 (Red Team Audit)'
    },

    // Liquidity Market
    liquidityMarket: {
      fedRateExpectations: '美联储利率预期',
      currentRate: '当前利率',
      expectedRate: '预期利率',
      probability: '概率',
      nextMeeting: '下次会议',
      yenCarryTrade: '日元套利预期',
      usdJpy: 'USD/JPY',
      carryYield: '套利收益',
      riskLevel: '风险等级',
      marketSentiment: '市场情绪'
    },

    // Detailed Stats
    stats: {
      fedRate: '美联储利率',
      yenCarry: '日元套利',
      rate: '利率',
      yield: '收益率',
      risk: '风险'
    },

    // Detailed Stats Labels
    detailedStats: {
      fedRate: '美联储利率',
      jpyCarry: '日元套利',
      ethWhale: 'ETH 生态资金流',
      solWhale: 'SOL 生态资金流',
      impliedRate: '隐含利率',
      range: '区间',
      restrictive: '限制性',
      price: '价格',
      change5d: '5日变化',
      dovishLabel: '鸽派',
      calmRisk: '冷静风险',
      stableRange: '稳定区间',
      devaluation: '贬值',
      stableCoin24h: '24h 稳定币流向 (交易所)',
      token24h: '24h 代币净流向 (巨鲸仓位)',
      stableCoin7d: '7d 稳定币流向 (交易所)',
      token7d: '7d 代币净流向 (巨鲸仓位)',
      bullish: '看涨',
      bearish: '看跌',
      // New specific keys
      fedTitle: "美联储利率预期 (30天期货)",
      fedBadge: "中性 (预期稳定)",
      restrictiveHigh: "限制性 (高位)",
      japanTitle: "日本宏观 (美元/日元)",
      japanBadge: "日元升值 (避险/利空)",
      weakYenRisk: "弱日元 (干预风险)",
      appreciation: "升值",
      // Macro Status Mapping
      status: {
        dovish: "鸽派 (利好流动性)",
        hawkish: "鹰派 (压力增加)",
        neutral: "中性 (预期平稳)",
        critical: "极高风险 (日元干预)",
        weakYen: "弱势日元 (风险偏好)",
        strongYen: "日元走强 (抛售风险)"
      }
    },

    // Whale Analytics
    whaleAnalytics: {
      selectChain: '选择链',
      ethereum: '以太坊',
      solana: 'SOL',
      totalHoldings: '总持仓',
      topWhales: 'Top 巨鲸',
      last24h: '24小时变化',
      address: '地址',
      balance: '余额',
      change24h: '24h 变化'
    },

    // Whale Data
    whaleData: {
      volume24h: '24h 成交量',
      holders: '持币地址',
      concentration: '集中度'
    },

    // Whale Section
    whale: {
      volume24h: '24h 成交量',
      activeWhales: '活跃巨鲸',
      stableCoinFlow: '稳定币流量',
      tokenFlow: '代币流量',
      whaleVolume: '巨鲸异动量',
      globalVolume: '全局成交量',
      leverage: '杠杆',
      volatility: '波动率',
      longLiquidation: '多头清算',
      shortLiquidation: '空头清算',
      increase: '增加',
      decrease: '减少',
      liquidationContext: '清算数据',
      volumeVsVolatility: '全局成交量 vs 波动率'
    },

    // News Items
    newsItems: [
      {
        title: 'BTC突破$98,000大关，创历史新高',
        summary: '比特币今日突破98,000美元，市场情绪高涨，机构投资者持续买入...',
        time: '2小时前',
        source: 'CoinDesk'
      },
      {
        title: '以太坊升级即将到来，Vitalik发布最新路线图',
        summary: 'Vitalik Buterin在推特发布以太坊2024年技术路线图，重点关注扩容和安全性...',
        time: '5小时前',
        source: 'Ethereum Foundation'
      },
      {
        title: 'Solana生态TVL突破50亿美元',
        summary: 'Solana DeFi生态持续增长，总锁定价值突破50亿美元大关...',
        time: '8小时前',
        source: 'DeFi Llama'
      }
    ],

    // Market Stats
    marketStats: {
      dxy: {
        name: 'DXY',
        description: '美元指数'
      },
      vix: {
        name: 'VIX',
        description: '波动率指数'
      },
      fear: {
        name: '恐慌指数',
        description: '市场恐慌程度'
      },
      sentiment: {
        name: '情绪指数',
        description: '市场情绪'
      },
      dxyLabel: 'DXY',
      vixLabel: 'VIX',
      usTreasury: '美国国债',
      fearGreed: '恐慌贪婪',
      dollarStrong: '美元强势',
      yieldUp: '收益率上涨',
      panic: '恐慌',
      // New interpretations
      dxyInterpretation: "美元走弱 (利好资产)",
      yieldInterpretation: "高位 (利空资产)",
      vixInterpretation: "情绪平稳 (利好资产)",
      greedInterpretation: "贪婪 (注意风险)"
    },

    // Crypto Cards
    crypto: {
      btcDesc: '宏观流动性宽松，但短期抛售压力大，机构利好未能提振价格。等待RSI/资金费率回暖确认短期底部。',
      ethDesc: 'RWA和量子计算叙事支撑基本面，但价格跌幅大于BTC。关注是否能借机构叙事强势反弹。',
      solDesc: '跌幅最大，RSI接近超卖区域（38.8）。高波动性资产在风险抛售中首当其冲。',
      bnbDesc: '相对抗跌，跌幅小于多数主要币种，资金费率接近中性，显示相对稳定。',
      dogeDesc: '随大盘下跌，但资金费率为正，显示散户情绪仍偏多头，若持续下跌易触发清算。'
    },

    // Sentiment Analysis
    sentimentAnalysis: {
      title: '情绪指数分析',
      overall: '整体情绪',
      fearGreedIndex: '恐慌贪婪指数',
      socialSentiment: '社交媒体情绪',
      tradingVolume: '交易量情绪',
      marketDominance: '市场主导地位',
      volatility: '波动性',
      extremeFear: '极度恐慌',
      fear: '恐慌',
      neutral: '中性',
      greed: '贪婪',
      extremeGreed: '极度贪婪'
    },

    // Sentiment Status
    sentiment: {
      neutral: '中性',
      bullish: '看涨',
      bearish: '看跌',
      index: '指数',
      sentiment7d: '7D 情绪指标',
      signal: '信号强度',
      risk: '观察建议 / 执行策略',
      riskLevels: {
        extreme: '风险极高 (信号缺失)',
        high: '高风险 (处于迷雾)',
        mid: '风险中等 (震荡博弈)',
        low: '风险较低 (趋势确认)',
        stable: '极低风险 (多维共振)'
      },
      signals: {
        EXECUTE: '立即执行',
        PROBE: '小幅试探',
        OBSERVE: '持币观察',
        NO_TRADE: '暂无机会',
        NEUTRAL: '中性待定'
      }
    },

    // News Feed
    news: {
      title: '实时资讯',
      readMore: '阅读更多',
      bearish: '看跌',
      bullish: '看涨',
      neutral: '中性',
      impulse: '脉冲',
      items: [
        {
          title: 'BTC突破$98,000大关，创历史新高',
          description: '比特币今日突破98,000美元，市场情绪高涨，机构投资者持续买入...'
        },
        {
          title: '以太坊升级即将到来，Vitalik发布最新路线图',
          description: 'Vitalik Buterin推特发���以太坊2024年技术路线图，重点关注扩容和安全性...'
        },
        {
          title: 'Solana生态TVL突破50亿美元',
          description: 'Solana DeFi生态持续增长，总锁定价值突破50亿美元大关...'
        },
        {
          title: 'SEC批准比特币现货ETF申请',
          description: '美国证监会批准多家机构的比特币现货ETF申请，加密货币市场迎来重大利好...'
        },
        {
          title: 'DeFi协议总锁定价值创新高',
          description: '去中心化金融协议的总锁定价值突破1000亿美元，标志着DeFi生态的持续增长...'
        },
        {
          title: '比特币挖矿难度调整至历史新高',
          description: '比特币网络挖矿难度再次调整，达到历史最高水平，显示网络安全性持续增强...'
        },
        {
          title: '以太坊Gas费降至历史低位',
          description: '随着Layer 2解决方案的普及，以太坊主网Gas费用大幅下降，用户体验显著改善...'
        },
        {
          title: 'NFT市场交易量回暖',
          description: 'NFT市场在经历低迷后逐渐回暖，多个蓝筹项目交易量明显上升...'
        },
        {
          title: '加密货币监管框架即将出台',
          description: '多国政府正在制定加密货币监管框架，行业合规化进程加速...'
        }
      ]
    },

    // Buy Me Tea
    donation: {
      title: '☕ 请我喝茶',
      subtitle: '感谢支持！您的打赏将用于数据服务和网站维护',
      paymentMethod: '支付方式',
      alipay: '支付宝',
      walletAddress: 'SOL 钱包地址',
      alipayAccount: '支付宝账号',
      copyAddress: '复制',
      copied: '已复制！',
      scanQR: '扫码转账（自定义金额）',
      scanAlipay: '扫码支付（自定义金额）',
      thankYou: '感谢您的支持！',
      solanaBlink: 'Solana Blink (一键赞赏)',
      stablecoinSupport: '支持 SOL / USDC / USDT',
      openBlink: '在钱包中打开'
    },

    // Footer
    footer: {
      platform: '实时监测平台',
      disclaimer: '免责声明：本网站提供的信息仅供参考，不构成投资议。加密货币投有风险，请谨慎决策。',
      rights: '© 2024 AI 鲸鱼监控与量化交易V2.0. 保留所有权利.'
    }
  },

  en: {
    // Header
    title: 'AI Whale & Quantitative Trading V2.0',
    subtitle: 'WHALE MONITOR & QUANTITATIVE TRADING V2.0',
    language: 'Language',

    // Navigation
    nav: {
      liquidity: 'Liquidity Sentiment',
      aiCopyTrading: 'AI Copy Trading',
      buyMeTea: 'Buy Me a Tea'
    },

    header: {
      liquidity: 'Liquidity',
      volume: 'Volume',
      marketCap: 'Market Cap'
    },

    // Market Analysis
    marketAnalysis: {
      title: 'AI Data Analysis Insights',
      updateTime: 'Update Status',
      content: '🔄 Awaiting the latest market judgment data from Dolores, please refresh later...',
      riskOn: 'Risk-On',
      expand: 'Expand Full Text',
      collapse: 'Collapse'
    },

    // Sections
    sections: {
      liquidityMarket: 'Liquidity Sentiment Analysis',
      whaleAnalytics: 'Whale Analytics',
      marketStats: 'Market Statistics',
      cryptoSentiment: 'Cryptocurrency Sentiment'
    },

    // AI Copy Trading
    aiTrading: {
      accountStats: 'Account Value',
      initialValue: 'Initial Amount',
      currentValue: 'Current Value',
      todayChange: 'Today',
      strategyDesc: 'AI Quantitative Strategy (4H), successfully running for',
      runningTimePlaceholder: '-- days -- hours',
      tabs: {
        current: 'Current Holdings',
        history: 'History',
        decisions: 'Model Decisions'
      },
      positionProfitLoss: 'Position Profit/Loss',
      remainingFunds: 'Remaining Funds',
      holding: 'Holdings',
      openPrice: 'Open Price',
      currentPrice: 'Current Price',
      stopLoss: 'Stop Loss Price',
      takeProfit: 'Take Profit Price',
      profitLoss: 'Profit/Loss',
      longMultiple: 'Long',
      shortMultiple: 'Short',
      // History tab
      historyStats: {
        totalProfitLoss: 'Total Profit/Loss',
        winRate: 'Win Rate',
        tradeCount: 'Trade Count'
      },
      long: 'Long',
      short: 'Short',
      closePrice: 'Close Price',
      quantity: 'Quantity',
      leverage: 'Leverage',
      // Decisions tab
      updateTime: 'Latest',
      marketAnalysis: 'Market Analysis',
      actions: 'Actions',
      hold: 'HOLD',
      rejected: 'REJECTED',
      marketLogic: 'Logic',
      riskWarning: 'Rejection Reason',
      position: 'Position',
      profitCurve: 'Profit Curve',
      cashBalance: 'Cash Balance',
      noPositions: 'No Positions',
      noHistory: 'No Trade History',
      decisionDetail: 'Decision Details',
      logicLabel: 'Logic',
      entryLabel: 'Entry',
      exitLabel: 'Exit',
      btcBenchmark: 'BTC Benchmark',
      confidence: 'Confidence',
      technicalSignal: 'Technical Signal',
      macroOnChain: 'Macro & On-Chain',
      quantitative: 'Quantitative (Qlib/Z-Vol)',
      regimeSafety: 'Regime Safety (Knife/Rocket)',
      portfolioStatus: 'Portfolio Status',
      redTeamAudit: 'Red Team Audit'
    },

    // Liquidity Market
    liquidityMarket: {
      fedRateExpectations: 'Fed Rate Expectations',
      currentRate: 'Current Rate',
      expectedRate: 'Expected Rate',
      probability: 'Probability',
      nextMeeting: 'Next Meeting',
      yenCarryTrade: 'Yen Carry Trade',
      usdJpy: 'USD/JPY',
      carryYield: 'Carry Yield',
      riskLevel: 'Risk Level',
      marketSentiment: 'Market Sentiment'
    },

    // Detailed Stats
    stats: {
      fedRate: 'Fed Rate',
      yenCarry: 'Yen Carry',
      rate: 'Rate',
      yield: 'Yield',
      risk: 'Risk'
    },

    // Detailed Stats Labels
    detailedStats: {
      fedRate: 'Fed Rate',
      jpyCarry: 'Yen Carry',
      ethWhale: 'ETH Capital Flow',
      solWhale: 'SOL Capital Flow',
      impliedRate: 'Implied Rate',
      range: 'Range',
      restrictive: 'Restrictive',
      price: 'Price',
      change5d: '5d Change',
      dovishLabel: 'Dovish',
      calmRisk: 'Calm Risk',
      stableRange: 'Stable Range',
      devaluation: 'Devaluation',
      stableCoin24h: '24h Stablecoin Flow (Exchanges)',
      token24h: '24h Token Flow (Whale Accumulation)',
      stableCoin7d: '7d Stablecoin Flow (Exchanges)',
      token7d: '7d Token Flow (Whale Accumulation)',
      bullish: 'Bullish',
      bearish: 'Bearish',
      // New specific keys
      fedTitle: "Fed Rate Expectations (30d Futures)",
      fedBadge: "Neutral (Stable)",
      restrictiveHigh: "Restrictive (High)",
      japanTitle: "Japan Macro (USD/JPY)",
      japanBadge: "JPY Appreciation (Risk/Bearish)",
      weakYenRisk: "Weak Yen (Intervention Risk)",
      appreciation: "Appreciation",
      // Macro Status Mapping
      status: {
        dovish: "Dovish (Bullish)",
        hawkish: "Hawkish (Bearish)",
        neutral: "Neutral (Stable)",
        critical: "Critical (Intervention)",
        weakYen: "Weak Yen (Risk-On)",
        strongYen: "Strong Yen (Deleveraging)"
      }
    },

    // Whale Analytics
    whaleAnalytics: {
      selectChain: 'Select Chain',
      ethereum: 'Ethereum',
      solana: 'SOL',
      totalHoldings: 'Total Holdings',
      topWhales: 'Top Whales',
      last24h: '24h Change',
      address: 'Address',
      balance: 'Balance',
      change24h: '24h Change'
    },

    // Whale Data
    whaleData: {
      volume24h: '24h Volume',
      holders: 'Holders',
      concentration: 'Concentration'
    },

    // Whale Section
    whale: {
      volume24h: '24h Volume',
      activeWhales: 'Active Whales',
      stableCoinFlow: 'Stablecoin Flow',
      tokenFlow: 'Token Flow',
      whaleVolume: 'Whale Tx Vol',
      globalVolume: 'Global Volume',
      leverage: 'Leverage',
      volatility: 'Volatility',
      longLiquidation: 'Long Liquidation',
      shortLiquidation: 'Short Liquidation',
      increase: 'Increase',
      decrease: 'Decrease',
      liquidationContext: 'Liquidation Context',
      volumeVsVolatility: 'Global Vol vs Volatility'
    },

    // News Items
    newsItems: [
      {
        title: 'BTC Breaks $98,000 Barrier, Sets New Record',
        summary: 'Bitcoin breaks through the $98,000 mark today, market sentiment is high, institutional investors continue to buy...',
        time: '2 hours ago',
        source: 'CoinDesk'
      },
      {
        title: 'Ethereum Upgrade Coming Soon, Vitalik Releases Latest Roadmap',
        summary: 'Vitalik Buterin releases Ethereum 2024 technical roadmap on Twitter, focusing on scalability and security...',
        time: '5 hours ago',
        source: 'Ethereum Foundation'
      },
      {
        title: 'Solana Ecosystem TVL Surpasses $5 Billion',
        summary: 'Solana DeFi ecosystem continues to grow, total value locked surpasses the $5 billion mark...',
        time: '8 hours ago',
        source: 'DeFi Llama'
      }
    ],

    // Market Stats
    marketStats: {
      dxy: {
        name: 'DXY',
        description: 'US Dollar Index'
      },
      vix: {
        name: 'VIX',
        description: 'Volatility Index'
      },
      fear: {
        name: 'Fear Index',
        description: 'Market Fear Level'
      },
      sentiment: {
        name: 'Sentiment',
        description: 'Market Sentiment'
      },
      dxyLabel: 'DXY',
      vixLabel: 'VIX',
      usTreasury: 'US Treasury',
      fearGreed: 'Fear & Greed',
      dollarStrong: 'Dollar Strong',
      yieldUp: 'Yield Up',
      panic: 'Panic',
      // New interpretations
      dxyInterpretation: "Dollar Weakening (Bullish)",
      yieldInterpretation: "High Levels (Bearish)",
      vixInterpretation: "Sentiment Calm (Bullish)",
      greedInterpretation: "Greed (Risk Alert)"
    },

    // Crypto Cards
    crypto: {
      btcDesc: 'Macro liquidity is loose, but short-term selling pressure is high. Institutional good news failed to boost price. Waiting for RSI/Funding rates to recover to confirm local bottom.',
      ethDesc: 'RWA and Quantum Computing narratives support fundamentals, but price drop exceeds BTC. Watch for potential strong rebound driven by institutional narratives.',
      solDesc: 'Largest drop, RSI nearing oversold territory (38.8). High-volatility assets take the hit first in risk-off selling.',
      bnbDesc: 'Relatively resilient, smaller drop than most majors, funding rate near neutral, indicating relative stability.',
      dogeDesc: 'Dropping with the market, but funding rate is positive, indicating retail sentiment remains bullish; risk of liquidation if drop continues.'
    },

    // Sentiment Analysis
    sentimentAnalysis: {
      title: 'Sentiment Analysis',
      overall: 'Overall Sentiment',
      fearGreedIndex: 'Fear & Greed Index',
      socialSentiment: 'Social Media Sentiment',
      tradingVolume: 'Trading Volume Sentiment',
      marketDominance: 'Market Dominance',
      volatility: 'Volatility',
      extremeFear: 'Extreme Fear',
      fear: 'Fear',
      neutral: 'Neutral',
      greed: 'Greed',
      extremeGreed: 'Extreme Greed'
    },

    // Sentiment Status
    sentiment: {
      neutral: 'Neutral',
      bullish: 'Bullish',
      bearish: 'Bearish',
      index: 'Index',
      sentiment7d: '7D Sentiment Index',
      signal: 'Signal Strength',
      risk: 'Observation / Execution',
      riskLevels: {
        extreme: 'Extreme Risk (No Signal)',
        high: 'High Risk (Uncertain)',
        mid: 'Mid Risk (Sideways)',
        low: 'Low Risk (Confirmed)',
        stable: 'Very Low Risk (Stable)'
      },
      signals: {
        EXECUTE: 'EXECUTE',
        PROBE: 'PROBE',
        OBSERVE: 'OBSERVE',
        NO_TRADE: 'NO TRADE',
        NEUTRAL: 'NEUTRAL'
      }
    },

    // News Feed
    news: {
      title: 'Real-Time News',
      readMore: 'Read More',
      bearish: 'Bearish',
      bullish: 'Bullish',
      neutral: 'Neutral',
      impulse: 'Impulse',
      items: [
        {
          title: 'BTC Breaks $98,000 Barrier, Sets New Record',
          description: 'Bitcoin breaks through the $98,000 mark today, market sentiment is high, institutional investors continue to buy...'
        },
        {
          title: 'Ethereum Upgrade Coming Soon, Vitalik Releases Latest Roadmap',
          description: 'Vitalik Buterin releases Ethereum 2024 technical roadmap on Twitter, focusing on scalability and security...'
        },
        {
          title: 'Solana Ecosystem TVL Surpasses $5 Billion',
          description: 'Solana DeFi ecosystem continues to grow, total value locked surpasses the $5 billion mark...'
        },
        {
          title: 'SEC Approves Bitcoin Spot ETF Applications',
          description: 'The US Securities and Exchange Commission approves multiple institutional Bitcoin spot ETF applications, bringing major利好 to the cryptocurrency market...'
        },
        {
          title: 'DeFi Protocol TVL Reaches New High',
          description: 'The total value locked in decentralized finance protocols surpasses $100 billion, marking the continued growth of the DeFi ecosystem...'
        },
        {
          title: 'Bitcoin Mining Difficulty Adjusted to New High',
          description: 'Bitcoin network mining difficulty is adjusted again, reaching a new high level, indicating continuous enhancement of network security...'
        },
        {
          title: 'Ethereum Gas Fees Drop to Historical Low',
          description: 'With the popularization of Layer 2 solutions, Ethereum mainnet gas fees have significantly decreased, improving user experience...'
        },
        {
          title: 'NFT Market Trading Volume Rebounds',
          description: 'The NFT market, after experiencing a downturn, gradually rebounds, with trading volumes of multiple blue-chip projects clearly increasing...'
        },
        {
          title: 'Cryptocurrency Regulation Frameworks Soon to be Released',
          description: 'Governments in multiple countries are formulating cryptocurrency regulation frameworks, accelerating the industry\'s compliance process...'
        }
      ]
    },

    // Buy Me Tea
    donation: {
      title: '☕ Buy Me Tea',
      subtitle: 'Thank you for your support! Your donation will be used for data services and website maintenance',
      paymentMethod: 'Payment Method',
      alipay: 'Alipay',
      walletAddress: 'SOL Wallet Address',
      alipayAccount: 'Alipay Account',
      copyAddress: 'Copy',
      copied: 'Copied!',
      scanQR: 'Scan to Transfer (Custom Amount)',
      scanAlipay: 'Scan to Pay (Custom Amount)',
      thankYou: 'Thank you for your support! 🙏',
      solanaBlink: 'Solana Blink (One-click)',
      stablecoinSupport: 'Supports SOL / USDC / USDT',
      openBlink: 'Open in Wallet'
    },

    // Footer
    footer: {
      platform: 'Real-Time Monitoring Platform',
      disclaimer: 'Disclaimer: The information provided on this website is for reference only and does not constitute investment advice. Cryptocurrency investment is risky, please make decisions carefully.',
      rights: '© 2024 AI Whale & Quantitative Trading V2.0. All rights reserved.'
    }
  }
};

export type Language = 'zh' | 'en';
export type TranslationKey = typeof translations.zh;