import { useEffect, useState } from "react";
import { useLanguage } from "@/app/i18n/LanguageContext";
import { fetchMarketStats, MarketStats as MarketStatsType } from "@/lib/api";

interface StatItem {
  label: string;
  value: string;
  change: string;
  trend: 'up' | 'down';
  interpretation: string;
  color: string;
}

export function MarketStats() {
  const { t, language } = useLanguage();
  const [marketData, setMarketData] = useState<MarketStatsType | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await fetchMarketStats();
        setMarketData(data);
      } catch (e) {
        console.error("Failed to fetch market stats", e);
      }
    }
    loadData();
  }, []);

  // Helper to safely format value
  const fmt = (val: any) => val ? Number(val).toFixed(2) : "--";
  const fmtChange = (val: any) => val ? (Number(val) > 0 ? "+" : "") + Number(val).toFixed(2) + "%" : "--";

  // Logic for dynamic interpretation
  const getLogic = (type: 'dxy' | 'us10y' | 'vix' | 'fg', value: any, change: any) => {
    const valNum = Number(value || 0);
    const changeNum = Number(change || 0);
    const isUp = changeNum > 0;
    const isZh = language === 'zh';

    let text = "--";
    let color = "text-[#8E9297]"; // Neutral gray default
    let sentimentType = 'neutral';

    if (type === 'dxy') {
      // DXY: Up = Bearish for risk assets (Red), Down = Bullish (Green)
      if (isZh) {
        text = isUp ? "美元走强 (利空资产)" : "美元走弱 (利好资产)";
      } else {
        text = isUp ? "Dollar Strong (Bearish)" : "Dollar Weak (Bullish)";
      }
      color = isUp ? "text-[var(--sentiment-bearish)]" : "text-[var(--sentiment-bullish)]";
      sentimentType = isUp ? 'bearish' : 'bullish';
    }
    else if (type === 'us10y') {
      // Yields: Up = Bearish (Red), Down = Bullish (Green)
      if (isZh) {
        text = isUp ? "收益率上行 (利空资产)" : "收益率下行 (利好资产)";
      } else {
        text = isUp ? "Yield Rising (Bearish)" : "Yield Falling (Bullish)";
      }
      color = isUp ? "text-[var(--sentiment-bearish)]" : "text-[var(--sentiment-bullish)]";
      sentimentType = isUp ? 'bearish' : 'bullish';
    }
    else if (type === 'vix') {
      // VIX: >20 Fear (Red/Orange), Rising (Red). Falling/Low (Green).
      if (valNum > 30) {
        text = isZh ? "极端恐慌 (高风险)" : "Extreme Fear (High Risk)";
        color = "text-[var(--sentiment-bearish)]";
        sentimentType = 'bearish';
      } else if (valNum > 20) {
        text = isZh ? "恐慌情绪 (注意风险)" : "Fear (Risk Alert)";
        color = "text-[var(--sentiment-warning)]";
        sentimentType = 'warning';
      } else if (isUp && Math.abs(changeNum) > 5) {
        text = isZh ? "恐慌升温 (利空)" : "Fear Rising (Bearish)";
        color = "text-[var(--sentiment-bearish)]";
        sentimentType = 'bearish';
      } else {
        text = isZh ? "情绪平稳 (利好)" : "Calm (Bullish)";
        color = "text-[var(--sentiment-bullish)]";
        sentimentType = 'bullish';
      }
    }
    else if (type === 'fg') {
      // Fear & Greed (0-100)
      if (valNum <= 25) {
        text = isZh ? "极度恐慌 (抄底机会?)" : "Extreme Fear (Buy?)";
        color = "text-[var(--sentiment-bullish)]";
        sentimentType = 'bullish';
      } else if (valNum <= 45) {
        text = isZh ? "恐慌" : "Fear";
        color = "text-[var(--sentiment-warning)]";
        sentimentType = 'warning';
      } else if (valNum <= 55) {
        text = isZh ? "中性" : "Neutral";
        color = "text-[var(--sentiment-neutral)]";
        sentimentType = 'neutral';
      } else if (valNum <= 75) {
        text = isZh ? "贪婪" : "Greed";
        color = "text-[var(--sentiment-bullish)]";
        sentimentType = 'bullish';
      } else {
        text = isZh ? "极度贪婪 (注意风险)" : "Extreme Greed (Risk)";
        color = "text-[var(--sentiment-bearish)]";
        sentimentType = 'bearish';
      }
    }

    return { text, color, sentimentType };
  }

  // Calculate logic for each
  const liquidityMonitor = (marketData?.macro?.liquidity_monitor || {}) as any;
  const fearGreedData = (marketData?.fear_greed || {}) as any;

  let fgChange = fearGreedData.change || 0;

  const dxyLogic = getLogic('dxy', liquidityMonitor.dxy?.price, liquidityMonitor.dxy?.change_5d_pct);
  const us10yLogic = getLogic('us10y', liquidityMonitor.us10y?.price, liquidityMonitor.us10y?.change_5d_pct);
  const vixLogic = getLogic('vix', liquidityMonitor.vix?.price, liquidityMonitor.vix?.change_5d_pct);
  const fgLogic = getLogic('fg', fearGreedData.value, fgChange);

  const stats: (StatItem & { sentimentType: string })[] = [
    {
      label: "DXY (Dollar)",
      value: fmt(liquidityMonitor.dxy?.price) !== "--" ? fmt(liquidityMonitor.dxy?.price) : "Loading...",
      change: fmtChange(liquidityMonitor.dxy?.change_5d_pct),
      trend: (liquidityMonitor.dxy?.change_5d_pct || 0) < 0 ? "down" : "up",
      interpretation: dxyLogic.text,
      color: dxyLogic.color,
      sentimentType: dxyLogic.sentimentType
    },
    {
      label: "US10Y (Yield)",
      value: fmt(liquidityMonitor.us10y?.price) !== "--" ? fmt(liquidityMonitor.us10y?.price) : "Loading...",
      change: fmtChange(liquidityMonitor.us10y?.change_5d_pct),
      trend: (liquidityMonitor.us10y?.change_5d_pct || 0) < 0 ? "down" : "up",
      interpretation: us10yLogic.text,
      color: us10yLogic.color,
      sentimentType: us10yLogic.sentimentType
    },
    {
      label: "VIX (Fear)",
      value: fmt(liquidityMonitor.vix?.price) !== "--" ? fmt(liquidityMonitor.vix?.price) : "Loading...",
      change: fmtChange(liquidityMonitor.vix?.change_5d_pct),
      trend: (liquidityMonitor.vix?.change_5d_pct || 0) < 0 ? "down" : "up",
      interpretation: vixLogic.text,
      color: vixLogic.color,
      sentimentType: vixLogic.sentimentType
    },
    {
      label: "Fear & Greed",
      value: fearGreedData.value || "Loading...",
      change: fgChange !== 0 ? (fgChange > 0 ? "+" : "") + fgChange.toFixed(1) + "%" : "--",
      trend: fgChange < 0 ? "down" : "up",
      interpretation: fgLogic.text,
      color: fgLogic.color,
      sentimentType: fgLogic.sentimentType
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {stats.map((stat: any, index: number) => (
        <div
          key={stat.label}
          className="relative bg-[#1a1a1a] border border-[#2D3139] p-4 overflow-hidden group rounded-sm hover:scale-[1.02] hover:shadow-[0_0_30px_var(--sentiment-bullish-bg)] transition-all duration-300"
        >
          <div className="relative z-10">
            <div className="flex flex-col mb-2">
              <div className="text-xs font-mono text-[#8E9297] uppercase tracking-wider mb-1">{stat.label}</div>
            </div>

            <div className="flex items-baseline gap-2 mb-2">
              <div className="text-2xl font-mono font-bold text-[#E8E8E8]">{stat.value}</div>
              <div className={`text-sm font-mono ${stat.color}`}>
                {stat.change}
              </div>
            </div>

            <div className="flex items-center gap-1">
              <div className={`text-xs font-sans px-1.5 py-0.5 rounded border border-opacity-30 ${stat.sentimentType === 'bullish' ? 'text-[var(--sentiment-bullish)] bg-[var(--sentiment-bullish-bg)] border-[var(--sentiment-bullish)]' :
                stat.sentimentType === 'bearish' ? 'text-[var(--sentiment-bearish)] bg-[var(--sentiment-bearish-bg)] border-[var(--sentiment-bearish)]' :
                  stat.sentimentType === 'warning' ? 'text-[var(--sentiment-warning)] bg-[var(--sentiment-warning-bg)] border-[var(--sentiment-warning)]' :
                    'text-[var(--sentiment-neutral)] bg-[var(--sentiment-neutral-bg)] border-[var(--sentiment-neutral)]'
                }`}>
                {stat.interpretation || "Neutral"}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}