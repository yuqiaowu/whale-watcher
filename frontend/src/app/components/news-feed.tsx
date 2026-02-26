import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";
import { useEffect, useState } from "react";
import { fetchMarketStats } from "@/lib/api";

interface NewsItem {
  title: string;
  description: string;
  sentiment: 'bearish' | 'bullish' | 'neutral';
  url?: string;
}

export function NewsFeed() {
  const { t, language } = useLanguage();
  const [news, setNews] = useState<NewsItem[]>([]);

  useEffect(() => {
    async function loadNews() {
      try {
        const stats = await fetchMarketStats();
        // Consolidate news from available categories
        // Priority: General -> Bitcoin -> Ethereum
        // In snapshot json: news.general.items, news.bitcoin.items

        // Check for AI Analysis first
        if (stats.ai_analysis && stats.ai_analysis.news_analysis) {
          const aiItems = stats.ai_analysis.news_analysis.slice(0, 10).map((item: any) => ({
            title: language === 'zh' ? (item.title_cn || item.title) : item.title,
            description: language === 'zh' ? (item.reason_cn || item.summary_cn || item.summary) : (item.reason_en || item.summary),
            sentiment: item.sentiment?.toLowerCase().includes('bull') ? 'bullish' :
              item.sentiment?.toLowerCase().includes('bear') ? 'bearish' : 'neutral',
            url: "#" // AI analysis might not strictly link back yet, or we need to find original URL. For now placeholder or match title.
          }));
          setNews(aiItems);
          return;
        }

        let items: any[] = [];
        if (stats.news?.bitcoin?.items) items = items.concat(stats.news.bitcoin.items);
        if (stats.news?.ethereum?.items) items = items.concat(stats.news.ethereum.items);
        if (stats.news?.general?.items) items = items.concat(stats.news.general.items);

        // If real data exists, use it
        if (items.length > 0) {
          const mappedNews: NewsItem[] = items.slice(0, 10).map((item: any) => {
            // Strip HTML tags from description
            const displayTitle = language === 'zh' ? (item.title_cn || item.title) : item.title;
            const displayDesc = language === 'zh' ? (item.summary_cn || item.summary) : item.summary;

            let rawDesc = displayDesc || displayTitle || "";
            // Remove <img> tags and other HTML
            const cleanDesc = rawDesc.replace(/<[^>]+>/g, '').trim();

            return {
              title: displayTitle,
              description: cleanDesc,
              sentiment: item.sentiment?.toLowerCase().includes('bull') ? 'bullish' :
                item.sentiment?.toLowerCase().includes('bear') ? 'bearish' : 'neutral',
              url: item.link || item.url
            };
          });
          setNews(mappedNews);
        } else {
          // Fallback to static data if API returns empty (e.g. scrape failure)
          fallbackToStatic();
        }
      } catch (e) {
        console.error("News fetch failed", e);
        fallbackToStatic();
      }
    }

    function fallbackToStatic() {
      const staticItems: NewsItem[] = t.news.items.map((item, index) => {
        const sentiments: ('bearish' | 'bullish' | 'neutral')[] = [
          'bearish', 'neutral', 'bearish', 'bearish', 'bearish',
          'neutral', 'neutral', 'neutral', 'neutral'
        ];
        return {
          title: item.title,
          description: item.description,
          sentiment: sentiments[index]
        };
      });
      setNews(staticItems);
    }

    loadNews();
  }, [t]);

  const getSentimentBadge = (sentiment: string) => {
    switch (sentiment) {
      case 'bearish':
        return (
          <div className="flex gap-2">
            <span className="px-3 py-1 text-xs font-mono bg-[var(--sentiment-bearish-bg)] text-[var(--sentiment-bearish)] border border-[var(--sentiment-bearish)]/40 rounded">
              {t.news.bearish}
            </span>
          </div>
        );
      case 'bullish':
        return (
          <div className="flex gap-2">
            <span className="px-3 py-1 text-xs font-mono bg-[var(--sentiment-bullish-bg)] text-[var(--sentiment-bullish)] border border-[var(--sentiment-bullish)]/40 rounded">
              {t.news.bullish}
            </span>
          </div>
        );
      default:
        return (
          <div className="flex gap-2">
            <span className="px-3 py-1 text-xs font-mono bg-[var(--sentiment-neutral-bg)] text-[var(--sentiment-neutral)] border border-[var(--sentiment-neutral)]/40 rounded">
              {t.news.neutral}
            </span>
          </div>
        );
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="bg-[#1a1a1a] border border-[#2D3139] overflow-hidden"
      style={{
        boxShadow: '0 0 20px rgba(57, 255, 20, 0.1)'
      }}
    >
      {/* News List */}
      <div className="divide-y divide-[#2D3139]">
        {news.map((item, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.05 * index }}
            whileHover={{
              backgroundColor: 'rgba(57, 255, 20, 0.03)',
              transition: { duration: 0.2 }
            }}
            className="px-6 py-4 cursor-pointer group"
            onClick={() => item.url && window.open(item.url, '_blank')}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-sans text-[#E8E8E8] mb-2 group-hover:text-[var(--sentiment-bullish)] transition-colors">
                  {item.title}
                </h4>
                <p className="text-xs font-sans text-[#8E9297] leading-relaxed line-clamp-2">
                  {item.description}
                </p>
              </div>
              <div className="flex-shrink-0">
                {getSentimentBadge(item.sentiment)}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}