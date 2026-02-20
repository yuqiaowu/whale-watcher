import { useState } from 'react';
import { motion } from 'motion/react';
import { WhaleChart } from '@/app/components/whale-chart';
import { useLanguage } from '@/app/i18n/LanguageContext';

type WhaleType = 'ETH' | 'SOL';

export function WhaleAnalytics({ data }: { data: any }) {
  const { t } = useLanguage();
  const [activeWhale, setActiveWhale] = useState<WhaleType>('ETH');

  const whaleInfo = data?.[activeWhale.toLowerCase()];
  const history = whaleInfo?.market?.history_60d || [];
  const stats24h = whaleInfo?.stats_24h || {};
  const statsHistory = whaleInfo?.stats_history || [];

  // Map history to chart format
  const chartDataRaw = history.slice(-24).map((p: any) => ({
    name: p.date.split(' ')[1], // HH:mm
    value: p.close,
    volume: p.volume,
    volatility: p.natr || p.rsi_14 // Prioritize NATR
  }));

  const formatFlow = (val: number) => {
    if (!val) return "0";
    const abs = Math.abs(val);
    if (abs >= 1000000) return (val / 1000000).toFixed(1) + "M";
    if (abs >= 1000) return (val / 1000).toFixed(1) + "K";
    return val.toFixed(0);
  };

  // Helper to determine if we have real accumulated history

  // Prepare Datasets (Strict Filtering - NO SIMULATION)
  const whaleCountData = statsHistory
    .filter((p: any) => p.whale_count !== undefined)
    .map((p: any) => ({ name: p.display_time, value: p.whale_count }));

  const stableFlowData = statsHistory
    .filter((p: any) => p.stablecoin_net_flow !== undefined)
    .map((p: any) => ({ name: p.display_time, value: p.stablecoin_net_flow }));

  const tokenFlowData = statsHistory
    .filter((p: any) => p.token_net_flow !== undefined)
    .map((p: any) => ({ name: p.display_time, value: p.token_net_flow }));

  const liqLeverageData = statsHistory
    .filter((p: any) => p.liquidation_long_usd !== undefined) // Only points whereเรา started recording these
    .map((p: any) => ({
      name: p.display_time,
      long: p.liquidation_long_usd,
      short: p.liquidation_short_usd,
      leverage: p.leverage_ratio
    }));

  const leverageVolumeData = statsHistory
    .filter((p: any) => p.leverage_ratio !== undefined && p.total_volume !== undefined)
    .map((p: any) => ({
      name: p.display_time,
      value: p.total_volume,
      leverage: p.leverage_ratio
    }));

  const volatilityData = chartDataRaw.map((p: any) => ({
    name: p.name,
    value: p.volume,
    volatility: p.volatility
  }));

  const getTrendText = (arr: any[], key = 'value') => {
    if (!arr || arr.length < 2) return '---';
    const current = arr[arr.length - 1][key];
    const prev = arr[arr.length - 2][key];
    if (current > prev) return t.whale.increase;
    if (current < prev) return t.whale.decrease;
    return '---';
  };

  const charts = [
    {
      title: `${t.whale.longLiquidation} & ${t.whale.shortLiquidation}`, // Updated title since leverage is gone
      subtitle: `${t.whale.longLiquidation}: ${formatFlow(stats24h.liquidation_long_usd || 0)} | ${t.whale.shortLiquidation}: ${formatFlow(stats24h.liquidation_short_usd || 0)}`,
      type: 'composed' as const,
      color: '#39FF14',
      data: liqLeverageData,
      seriesNames: {
        long: t.whale.longLiquidation,
        short: t.whale.shortLiquidation
        // leverage removed from here
      }
    },
    {
      title: `${t.whale.activeWhales}: ${stats24h.whale_count || '--'}`,
      subtitle: getTrendText(whaleCountData),
      type: 'line' as const,
      color: '#39FF14',
      data: whaleCountData,
      seriesNames: { value: t.whale.activeWhales }
    },
    {
      title: `${t.whale.stableCoinFlow}: ${formatFlow(stats24h.stablecoin_net_flow || 0)}`,
      subtitle: getTrendText(stableFlowData),
      type: 'area' as const,
      color: (stats24h.stablecoin_net_flow || 0) >= 0 ? '#39FF14' : '#FF3131',
      data: stableFlowData,
      seriesNames: { value: t.whale.stableCoinFlow }
    },
    {
      title: `${t.whale.tokenFlow}: ${formatFlow(stats24h.token_net_flow || 0)}`,
      subtitle: getTrendText(tokenFlowData),
      type: 'line' as const,
      color: (stats24h.token_net_flow || 0) >= 0 ? '#39FF14' : '#FF3131',
      data: tokenFlowData,
      seriesNames: { value: t.whale.tokenFlow }
    },
    {
      title: `${t.whale.whaleVolume} & ${t.whale.leverage}`,
      subtitle: (whaleInfo?.market?.liquidation_context || 'No data')
        .replace(/Long Liquidation/g, t.whale.longLiquidation)
        .replace(/Short Liquidation/g, t.whale.shortLiquidation),
      type: 'composed' as const,
      color: '#39FF14',
      data: leverageVolumeData,
      seriesNames: { volume: t.whale.whaleVolume, leverage: t.whale.leverage }
    },
    {
      title: `${t.whale.volatility}: ${whaleInfo?.market?.natr_percent?.toFixed(2) || '--'}%`,
      subtitle: t.whale.volumeVsVolatility,
      type: 'composed' as const,
      color: '#39FF14',
      data: volatilityData,
      seriesNames: {
        volume: t.whale.globalVolume,
        volatility: t.whale.volatility
      }
    },
  ];

  return (
    <div className="mb-8">
      {/* Tab Switcher */}
      <div className="flex items-center gap-4 mb-6 ml-4">
        {(['ETH', 'SOL'] as WhaleType[]).map((type) => (
          <motion.button
            key={type}
            onClick={() => setActiveWhale(type)}
            className={`
              relative px-6 py-2 font-mono font-medium tracking-wide
              transition-all duration-300
              ${activeWhale === type
                ? 'text-[#1a1a1a] bg-[#39FF14]'
                : 'text-[#8E9297] bg-[#1a1a1a] border border-[#2D3139] hover:border-[#39FF14] hover:text-[#39FF14]'
              }
            `}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <span className="relative z-10">
              {type === 'ETH' ? t.detailedStats.ethWhale : t.detailedStats.solWhale}
            </span>

            {activeWhale === type && (
              <motion.div
                className="absolute inset-0 bg-[#39FF14]"
                layoutId="activeTab"
                style={{
                  boxShadow: '0 0 20px rgba(57, 255, 20, 0.5), 0 0 40px rgba(57, 255, 20, 0.3)',
                  zIndex: -1
                }}
              />
            )}
          </motion.button>
        ))}
      </div>

      {/* Charts Grid */}
      <motion.div
        key={activeWhale}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        {charts.map((chart, index) => (
          <WhaleChart
            key={`${activeWhale}-${index}`}
            title={chart.title}
            subtitle={chart.subtitle}
            type={chart.type}
            color={chart.color}
            data={chart.data}
            index={index}
            // @ts-ignore
            seriesNames={chart.seriesNames}
          />
        ))}
      </motion.div>
    </div>
  );
}