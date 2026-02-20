import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";

interface DetailedStatProps {
  title: string;
  badge?: string;
  badgeColor?: string;
  items: Array<{
    label: string;
    value: string;
    sentiment?: string;
    highlight?: boolean;
  }>;
  index: number;
}

function DetailedStatCard({ title, badge, badgeColor, items, index }: DetailedStatProps) {
  const getSentimentClass = (sentiment: string) => {
    if (sentiment.includes('利多') || sentiment.includes('偏低') || sentiment.includes('鸽派') ||
      sentiment.includes('Bullish') || sentiment.includes('Low') || sentiment.includes('Dovish') ||
      sentiment.includes('看涨') || sentiment.includes('升值') || sentiment.includes('Appreciation') ||
      sentiment.includes('利好') || sentiment.includes('偏好')) {
      return 'text-[#39FF14] bg-[#39FF1422]';
    }
    return 'text-[#FF3131] bg-[#FF313122]';
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{
        scale: 1.02,
        boxShadow: "0 0 30px rgba(57, 255, 20, 0.2)"
      }}
      className="relative bg-[#1a1a1a] border border-[#2D3139] p-5 overflow-hidden group rounded-sm"
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-mono font-medium text-[#E8E8E8] pl-1 tracking-wide flex items-center gap-2">
          {(title.includes('Fed') || title.includes('美联储')) ? '🏛️' : (title.includes('Japan') || title.includes('日本')) ? '💴' : title.includes('ETH') ? 'Ξ' : title.includes('SOL') ? '◎' : ''}
          {title}
        </h3>
        {badge && (
          <span className={`text-[10px] px-2 py-0.5 rounded border border-opacity-30 ${badgeColor} border-current`}>
            {badge}
          </span>
        )}
      </div>

      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center justify-between">
            <span className="text-xs font-sans text-[#8E9297]">{item.label}</span>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-mono ${item.highlight ? 'text-[#E9B124] font-bold' : 'text-[#E8E8E8]'}`}>
                {item.value}
              </span>
              {item.sentiment && (
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${getSentimentClass(item.sentiment)}`}>
                  {item.sentiment}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Hover effect */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-transparent via-[#39FF1408] to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
        animate={{
          x: ['-100%', '100%'],
        }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: "linear"
        }}
      />
    </motion.div>
  );
}

export function DetailedStats({ data }: { data?: any }) {
  const { t } = useLanguage();

  // Extract real data
  const eth24hStats = data?.eth?.stats_24h || {};
  const eth7dStats = data?.eth?.stats_7d || data?.eth?.stats || {};
  const sol24hStats = data?.sol?.stats_24h || {};
  const sol7dStats = data?.sol?.stats_7d || data?.sol?.stats || {};

  // Helper for flow logic
  const getFlowLogic = (change: number | undefined) => {
    if (change === undefined || isNaN(Number(change))) return { value: "--", sentiment: "" };

    const valNum = Number(change);
    const isInflow = valNum > 0;
    const absVal = Math.abs(valNum);

    let valStr;
    if (absVal >= 1_000_000) {
      valStr = `${(absVal / 1_000_000).toFixed(1)}M`;
    } else if (absVal >= 1_000) {
      valStr = `${(absVal / 1_000).toFixed(1)}K`;
    } else {
      valStr = `${absVal.toFixed(0)}`;
    }

    return {
      value: `${isInflow ? '+' : '-'}${valStr}`,
      sentiment: isInflow ? t.detailedStats.bullish : t.detailedStats.bearish,
      isBullish: isInflow
    };
  };

  const eth24hStable = getFlowLogic(eth24hStats.stablecoin_net_flow);
  const eth24hToken = getFlowLogic(eth24hStats.token_net_flow);
  const eth7dStable = getFlowLogic(eth7dStats.stablecoin_net_flow);
  const eth7dToken = getFlowLogic(eth7dStats.token_net_flow);

  const sol24hStable = getFlowLogic(sol24hStats.stablecoin_net_flow);
  const sol24hToken = getFlowLogic(sol24hStats.token_net_flow);
  const sol7dStable = getFlowLogic(sol7dStats.stablecoin_net_flow);
  const sol7dToken = getFlowLogic(sol7dStats.token_net_flow);

  // Helper for macro status translations
  const translateMacroStatus = (statusStr: string | undefined) => {
    if (!statusStr || statusStr === "--") return "--";
    const s = statusStr.toLowerCase();
    const st = t.detailedStats.status as any;

    if (s.includes('dovish')) return st.dovish;
    if (s.includes('hawkish')) return st.hawkish;
    if (s.includes('critical')) return st.critical;
    if (s.includes('weak yen')) return st.weakYen;
    if (s.includes('strong yen')) return st.strongYen;
    if (s.includes('neutral')) return st.neutral;

    return statusStr;
  };

  const stats = [
    {
      title: t.detailedStats.fedTitle,
      badge: t.detailedStats.fedBadge,
      badgeColor: "bg-[#3B82F6]/20 text-[#60A5FA]",
      items: [
        { label: t.detailedStats.impliedRate, value: data?.fed_futures?.implied_rate ? `${data.fed_futures.implied_rate}%` : "--" },
        { label: t.detailedStats.range, value: translateMacroStatus(data?.fed_futures?.trend), highlight: true },
        { label: t.detailedStats.price, value: data?.fed_futures?.price ? `${data.fed_futures.price}` : "--" },
        { label: t.detailedStats.change5d, value: data?.fed_futures?.change_5d_bps ? `${data.fed_futures.change_5d_bps} bps` : "--", sentiment: t.sentiment.neutral }
      ]
    },
    {
      title: t.detailedStats.japanTitle,
      badge: t.detailedStats.japanBadge,
      badgeColor: "bg-[#FF3131]/20 text-[#FF3131]",
      items: [
        { label: t.detailedStats.price, value: data?.japan_rates?.price ? `${data.japan_rates.price}` : "--" },
        { label: t.detailedStats.range, value: translateMacroStatus(data?.japan_rates?.trend), highlight: true },
        { label: t.detailedStats.change5d, value: data?.japan_rates?.change_5d_pct ? `${data.japan_rates.change_5d_pct}%` : "--", sentiment: t.detailedStats.appreciation }
      ]
    },
    {
      title: t.detailedStats.ethWhale,
      items: [
        { label: t.detailedStats.stableCoin24h, value: eth24hStable.value, sentiment: eth24hStable.sentiment },
        { label: t.detailedStats.token24h, value: eth24hToken.value, sentiment: eth24hToken.sentiment },
        { label: t.detailedStats.stableCoin7d, value: eth7dStable.value, sentiment: eth7dStable.sentiment },
        { label: t.detailedStats.token7d, value: eth7dToken.value, sentiment: eth7dToken.sentiment }
      ]
    },
    {
      title: t.detailedStats.solWhale,
      items: [
        { label: t.detailedStats.stableCoin24h, value: sol24hStable.value, sentiment: sol24hStable.sentiment },
        { label: t.detailedStats.token24h, value: sol24hToken.value, sentiment: sol24hToken.sentiment },
        { label: t.detailedStats.stableCoin7d, value: sol7dStable.value, sentiment: sol7dStable.sentiment },
        { label: t.detailedStats.token7d, value: sol7dToken.value, sentiment: sol7dToken.sentiment }
      ]
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {stats.map((stat, index) => (
        <DetailedStatCard key={stat.title} {...stat} index={index} />
      ))}
    </div>
  );
}