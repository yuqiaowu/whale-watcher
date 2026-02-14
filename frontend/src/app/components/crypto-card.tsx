import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";

interface CryptoCardProps {
  symbol: string;
  name: string;
  price: string;
  change: string;
  rsi: string;
  rate: string;
  sentiment: string;
  sentimentScore: number;
  description: string;
  index: number;
}

export function CryptoCard({
  symbol,
  price,
  change,
  rsi,
  rate,
  sentiment,
  sentimentScore,
  description,
  index
}: CryptoCardProps) {
  const { t } = useLanguage();
  const isPositive = change.startsWith('+');

  const getSentimentColors = (s: string) => {
    if (s.includes('BULLISH') || s.includes('OVERSOLD') || s.includes('LONG')) return {
      border: 'border-[var(--sentiment-bullish)]',
      text: 'text-[var(--sentiment-bullish)]',
      bg: 'bg-[var(--sentiment-bullish-bg)]',
      shadow: 'var(--sentiment-bullish-bg)',
      bar: 'bg-[var(--sentiment-bullish)]',
      barShadow: 'var(--sentiment-bullish-bg)'
    };
    if (s.includes('BEARISH') || s.includes('OVERBOUGHT') || s.includes('SHORT')) return {
      border: 'border-[var(--sentiment-bearish)]',
      text: 'text-[var(--sentiment-bearish)]',
      bg: 'bg-[var(--sentiment-bearish-bg)]',
      shadow: 'var(--sentiment-bearish-bg)',
      bar: 'bg-[var(--sentiment-bearish)]',
      barShadow: 'var(--sentiment-bearish-bg)'
    };
    // NEUTRAL or others
    return {
      border: 'border-[var(--sentiment-neutral)]',
      text: 'text-[var(--sentiment-neutral)]',
      bg: 'bg-[var(--sentiment-neutral-bg)]',
      shadow: 'var(--sentiment-neutral-bg)',
      bar: 'bg-[var(--sentiment-neutral)]',
      barShadow: 'var(--sentiment-neutral-bg)'
    };
  };

  const colors = getSentimentColors(sentiment);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{
        scale: 1.05,
        boxShadow: "0 0 30px rgba(57, 255, 20, 0.2)"
      }}
      className="relative bg-[#1a1a1a] border border-[#2D3139] p-4 overflow-hidden group rounded-sm"
    >
      {/* Corner accent */}
      <div className="absolute top-0 right-0 w-20 h-20">
        <div className="absolute top-0 right-0 w-full h-full bg-gradient-to-br from-[#8E929733] to-transparent" />
      </div>

      {/* Glitch lines */}
      <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-50" />

      <div className="relative z-10">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-xl font-mono font-bold text-[#E8E8E8] mb-1 tracking-wide">{symbol}</h3>
            {/* <div className="text-xs font-sans text-[#8E9297]">{name}</div> */}
          </div>

          <motion.div
            animate={{
              scale: [1, 1.05, 1],
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: "easeInOut"
            }}
            className={`px-2 py-1 border ${colors.border} ${colors.text} ${colors.bg} text-[10px] font-mono font-bold uppercase tracking-wider rounded-sm`}
            style={{
              boxShadow: `0 0 8px ${colors.shadow}`
            }}
          >
            {sentiment} ({sentimentScore})
          </motion.div>
        </div>

        {/* Price */}
        <div className="flex items-baseline gap-3 mb-4">
          <div className="text-2xl font-mono font-bold text-[#E8E8E8]">{price}</div>
          <div className={`flex items-center gap-1 text-sm font-mono ${isPositive ? 'text-[var(--sentiment-bullish)]' : 'text-[var(--sentiment-bearish)]'
            }`}>
            {/* <Activity className="w-3 h-3" /> */}
            {change}
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-6 mb-4 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-[#8E9297]">RSI:</span>
            <span className="text-[#E8E8E8]">{rsi}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#8E9297]">{t.stats?.rate || 'Funding'}:</span>
            <span className="text-[#E8E8E8]">{rate}</span>
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-[#2a2f3e] mb-4 overflow-hidden rounded-full">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${sentimentScore}%` }}
            transition={{ delay: index * 0.1 + 0.3, duration: 1, ease: "easeOut" }}
            className={`h-full ${colors.bar}`}
            style={{
              boxShadow: `0 0 6px ${colors.barShadow}`
            }}
          />
        </div>

        {/* Description */}
        <div className="min-h-[60px]"> {/* Fixed height for alignment */}
          <p className="text-xs font-sans text-[#B0B3B8] leading-normal line-clamp-3">
            {description}
          </p>
        </div>
      </div>

      {/* Animated scan line */}
      <motion.div
        className="absolute left-0 w-full h-px bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-0 group-hover:opacity-100"
        animate={{
          y: [0, 300],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "linear"
        }}
      />
    </motion.div>
  );
}