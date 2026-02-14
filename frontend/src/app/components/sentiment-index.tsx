import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";

interface SentimentIndexProps {
  crypto: string;
  value: string;
  status: string;
  progress: number;
  index: number;
}

export function SentimentIndex({ crypto, value, status, progress, index }: SentimentIndexProps) {
  const { t } = useLanguage();

  const getCurrentRisk = () => {
    const rl = t.sentiment.riskLevels as any;
    if (progress >= 85) return rl.stable;
    if (progress >= 65) return rl.low;
    if (progress >= 40) return rl.mid;
    if (progress >= 15) return rl.high;
    return rl.extreme;
  };

  const getStatusColor = () => {
    const s = status.toUpperCase();
    if (s.includes('涨') || s.includes('BULLISH') || s.includes('OVERSOLD') || s.includes('EXECUTE') || s.includes('PROBE') || s.includes('LONG')) {
      return '#39FF14'; // Fluorescent Green
    } else if (s.includes('跌') || s.includes('BEARISH') || s.includes('OVERBOUGHT') || s.includes('SELL') || s.includes('SHORT')) {
      return '#FF3131'; // Alert Red
    } else if (s.includes('EXTREME') || s.includes('VOLATILE')) {
      return '#FFD60A'; // Warning Yellow
    }
    return '#E5E7EB'; // Neutral Gray
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{
        boxShadow: "0 0 30px rgba(57, 255, 20, 0.2)",
        scale: 1.02
      }}
      className="relative bg-[#1a1a1a] border border-[#2D3139] p-6 overflow-hidden group"
    >
      {/* Title */}
      <div className="text-xs font-mono text-[#8E9297] mb-3 tracking-wider">
        {crypto} {t.sentiment.index}
      </div>

      {/* Value */}
      <div className="text-4xl font-mono font-bold text-[#E8E8E8] mb-4 tracking-tight">
        {value}
      </div>

      {/* Status Tags */}
      <div className="flex items-center gap-2 mb-6">
        <span className="text-xs font-mono text-[#8E9297]">{t.sentiment.signal}</span>
        <span className="text-[#2D3139]">/</span>
        <span
          className="text-xs font-mono font-bold"
          style={{ color: getStatusColor() }}
        >
          {((t.sentiment.signals as any)[status]) || status}
        </span>
      </div>

      {/* Progress bar area */}
      <div className="relative mb-6">
        {/* Current Risk Indicator */}
        <motion.div
          initial={{ left: 0 }}
          animate={{ left: `${progress}%` }}
          transition={{ delay: index * 0.1 + 0.3, duration: 1 }}
          className="absolute -top-5 -translate-x-1/2 flex flex-col items-center"
        >
          <span className="text-[10px] font-mono whitespace-nowrap px-1 bg-[#1a1a1a] border border-gray-800 rounded" style={{ color: getStatusColor() }}>
            {getCurrentRisk()}
          </span>
          <div className="w-[1px] h-2 mb-1" style={{ backgroundColor: getStatusColor() }} />
        </motion.div>

        <div className="w-full h-1 bg-[#2a2f3e] overflow-hidden rounded-full">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ delay: index * 0.1 + 0.3, duration: 1, ease: "easeOut" }}
            className="h-full"
            style={{
              background: `linear-gradient(to right, ${getStatusColor()}dd, ${getStatusColor()})`,
              boxShadow: `0 0 10px ${getStatusColor()}33`
            }}
          />
        </div>
      </div>

      {/* Footer labels */}
      <div className="flex items-center justify-between text-[10px] font-sans text-[#5A5F6B] uppercase tracking-tighter">
        <span>{t.sentiment.riskLevels.extreme} (0%)</span>
        <span className="text-[#2D3139]">/</span>
        <span>{t.sentiment.riskLevels.stable} (100%)</span>
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