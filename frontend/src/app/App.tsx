import { CyberHeader } from "@/app/components/cyber-header";
import { MarketStats } from "@/app/components/market-stats";
import { MarketAnalysis } from "@/app/components/market-analysis";
import { DetailedStats } from "@/app/components/detailed-stats";
import { CryptoCard } from "@/app/components/crypto-card";
import { WhaleAnalytics } from "@/app/components/whale-analytics";
import { SentimentIndex } from "@/app/components/sentiment-index";
import { NewsFeed } from "@/app/components/news-feed";
import { AICopyTrading } from "@/app/components/ai-copy-trading";
import { LanguageProvider, useLanguage } from "@/app/i18n/LanguageContext";
import { motion } from "motion/react";
import { useState, useEffect } from "react";
import { fetchCryptoData, fetchMarketStats, fetchSummary, type CryptoDataResponse, type MarketStats as MarketStatsType } from "@/lib/api";

function AppContent() {
  const { t } = useLanguage();
  const [activePage, setActivePage] = useState('liquidity');
  const [marketStats, setMarketStats] = useState<MarketStatsType | null>(null);
  const [liveData, setLiveData] = useState<CryptoDataResponse["data"] | null>(null);
  const [runningTime, setRunningTime] = useState<string>("-- 天 --");

  useEffect(() => {
    async function initData() {
      try {
        const stats = await fetchMarketStats().catch((_e: Error) => null);
        if (stats) setMarketStats(stats);

        const cryptoResponse = await fetchCryptoData().catch((_e: Error) => null);
        if (cryptoResponse && cryptoResponse.data) {
          setLiveData(cryptoResponse.data);
        }

        const summary = await fetchSummary().catch((_e: Error) => null);
        if (summary && summary.startTime) {
          const start = new Date(summary.startTime);
          const now = new Date();
          const diffMs = now.getTime() - start.getTime();
          const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
          const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
          setRunningTime(`${diffDays} 天 ${diffHours}`);
        }
      } catch (e: any) {
        console.error("Init data error:", e);
      }
    }
    initData();
    const interval = setInterval(initData, 60000);
    return () => clearInterval(interval);
  }, []);

  const cryptoConfig = [
    { symbol: "BTC", name: "Bitcoin", descriptionKey: 'btcDesc' as const },
    { symbol: "ETH", name: "Ethereum", descriptionKey: 'ethDesc' as const },
    { symbol: "SOL", name: "Solana", descriptionKey: 'solDesc' as const },
    { symbol: "BNB", name: "Binance Coin", descriptionKey: 'bnbDesc' as const },
    { symbol: "DOGE", name: "Dogecoin", descriptionKey: 'dogeDesc' as const }
  ];

  // Helper to format price
  const formatPrice = (price: number) => {
    if (price < 1) return price.toFixed(4);
    if (price < 10) return price.toFixed(3);
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const cryptoData = cryptoConfig.map(config => {
    const live = liveData?.[config.symbol];
    return {
      ...config,
      price: live ? `$${formatPrice(live.price)}` : "Loading...",
      change: live?.change_24h !== undefined ? `${live.change_24h > 0 ? '+' : ''}${live.change_24h.toFixed(2)}%` : "---",
      rsi: live ? live.rsi_4h.toFixed(1) : "---",
      rate: live ? `${(live.funding_rate * 100).toFixed(4)}%` : "---",
      sentiment: live ? live.sentiment : "NEUTRAL",
      sentimentScore: live ? live.sentimentScore : 50
    };
  });

  return (
    <div className={`${activePage === 'aiTrading' ? 'h-screen overflow-hidden' : 'min-h-screen'} bg-gradient-to-br from-[#0A0C0E] via-[#14171A] to-[#0A0C0E] flex flex-col`}>
      {/* Background effects */}
      <div className="fixed inset-0 z-0">
        {/* Animated gradient orbs */}
        <motion.div
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.1, 0.2, 0.1],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: "easeInOut"
          }}
          className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#39FF14] rounded-full blur-[120px]"
        />
        <motion.div
          animate={{
            scale: [1.2, 1, 1.2],
            opacity: [0.1, 0.15, 0.1],
          }}
          transition={{
            duration: 10,
            repeat: Infinity,
            ease: "easeInOut"
          }}
          className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[#00ddff] rounded-full blur-[120px]"
        />
      </div>

      {/* Content */}
      <div className="relative z-10 flex flex-col flex-1 min-h-0">
        <CyberHeader activePage={activePage} onPageChange={setActivePage} />

        <main className={`container mx-auto px-4 flex-1 flex flex-col min-h-0 ${activePage === 'aiTrading' ? 'py-4' : 'py-8'}`}>
          {activePage === 'liquidity' ? (
            <>
              {/* AI Data Analysis - First Section */}
              <section className="mb-12">
                <MarketAnalysis />
              </section>

              {/* Market Overview */}
              <section className="mb-12">
                <motion.h2
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-xl font-mono font-medium mb-6 text-[#39FF14] flex items-center gap-3 tracking-wider"
                  style={{
                    textShadow: '0 0 10px rgba(57, 255, 20, 0.5), 0 0 20px rgba(57, 255, 20, 0.3)'
                  }}
                >
                  <span className="inline-block w-1 h-6 bg-[#39FF14] shadow-[0_0_10px_rgba(57,255,20,0.8)]" />
                  {t.sections.liquidityMarket}
                </motion.h2>

                <DetailedStats data={marketStats} />
                <MarketStats />
              </section>

              {/* Crypto Cards */}
              <section className="mb-12">
                <motion.h2
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 }}
                  className="text-xl font-mono font-medium mb-6 text-[#39FF14] flex items-center gap-3 tracking-wider"
                  style={{
                    textShadow: '0 0 10px rgba(57, 255, 20, 0.5), 0 0 20px rgba(57, 255, 20, 0.3)'
                  }}
                >
                  <span className="inline-block w-1 h-6 bg-[#39FF14] shadow-[0_0_10px_rgba(57,255,20,0.8)]" />
                  {t.sections.cryptoSentiment}
                </motion.h2>

                <div className="grid grid-cols-2 gap-4 mb-4">
                  <SentimentIndex
                    crypto={`ETH ${t.sentiment.sentiment7d}`}
                    value={marketStats?.eth?.stats?.confidence_score ? `${marketStats.eth.stats.confidence_score.toFixed(1)}%` : "Loading"}
                    status={marketStats?.eth?.stats?.action_signal || "NEUTRAL"}
                    progress={marketStats?.eth?.stats?.confidence_score || 50}
                    index={0}
                  />
                  <SentimentIndex
                    crypto={`SOL ${t.sentiment.sentiment7d}`}
                    value={marketStats?.sol?.stats?.confidence_score ? `${marketStats.sol.stats.confidence_score.toFixed(1)}%` : "Loading"}
                    status={marketStats?.sol?.stats?.action_signal || "NEUTRAL"}
                    progress={marketStats?.sol?.stats?.confidence_score || 50}
                    index={1}
                  />
                </div>

                <div className="grid grid-cols-5 gap-4">
                  {cryptoData.map((crypto, index) => (
                    <CryptoCard
                      key={crypto.symbol}
                      {...crypto}
                      description={liveData?.[crypto.symbol]?.description || t.crypto[crypto.descriptionKey]}
                      index={index + 2}
                    />
                  ))}
                </div>
              </section>

              {/* Whale Analytics */}
              <section>
                <motion.h2
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.4 }}
                  className="text-xl font-mono font-medium mb-6 text-[#39FF14] flex items-center gap-3 tracking-wider"
                  style={{
                    textShadow: '0 0 10px rgba(57, 255, 20, 0.5), 0 0 20px rgba(57, 255, 20, 0.3)'
                  }}
                >
                  <span className="inline-block w-1 h-6 bg-[#39FF14] shadow-[0_0_10px_rgba(57,255,20,0.8)]" />
                  {t.sections.whaleAnalytics}
                </motion.h2>

                <WhaleAnalytics />
              </section>

              {/* News Feed Section */}
              <section className="mb-12">
                <motion.h2
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.6 }}
                  className="text-xl font-mono font-medium mb-6 text-[#39FF14] flex items-center gap-3 tracking-wider"
                  style={{
                    textShadow: '0 0 10px rgba(57, 255, 20, 0.5), 0 0 20px rgba(57, 255, 20, 0.3)'
                  }}
                >
                  <span className="inline-block w-1 h-6 bg-[#39FF14] shadow-[0_0_10px_rgba(57,255,20,0.8)]" />
                  {t.news.title}
                </motion.h2>
                <NewsFeed />
              </section>
            </>
          ) : (
            <>
              {/* AI Copy Trading Page */}
              <section className="flex-1 flex flex-col min-h-0">
                <motion.h2
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-sm font-mono font-normal mb-4 text-[#8E9297] flex items-center gap-2 tracking-wide"
                >
                  <span className="inline-block w-0.5 h-4 bg-[#39FF14]/60 shadow-[0_0_6px_rgba(57,255,20,0.4)]" />
                  <span className="opacity-90">4小时线为基准的AI量化策略，已成功运行 <span className="text-[#39FF14] font-medium">{runningTime}</span> 小时</span>
                </motion.h2>
                <AICopyTrading />
              </section>
            </>
          )}

          {activePage !== 'aiTrading' && (
            <motion.footer
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1 }}
              className="mt-16 pt-8 border-t border-[#2D3139] text-center"
            >
              <div className="flex items-center justify-center gap-2 text-[#8E9297] text-sm font-mono">
                <div className="w-2 h-2 bg-[#39FF14] rounded-full animate-pulse shadow-[0_0_8px_rgba(57,255,20,0.6)]" />
                <span>CRYPTO_DATA</span>
                <span>|</span>
                <span>{t.footer.platform}</span>
                <span>|</span>
                <span>© 2025</span>
              </div>
            </motion.footer>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <AppContent />
    </LanguageProvider>
  );
}