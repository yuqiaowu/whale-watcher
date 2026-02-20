import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";
import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { fetchMarketStats } from "@/lib/api";

export function MarketAnalysis() {
  const { t, language } = useLanguage();
  const [isExpanded, setIsExpanded] = useState(false);
  const [analysisText, setAnalysisText] = useState("");

  // Get current time formatted
  const now = new Date();
  const updateTime = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

  useEffect(() => {
    async function loadAnalysis() {
      try {
        const stats = await fetchMarketStats();

        // Prioritize Agent Decision Analysis (DeepSeek - Telegram source)
        // Backend key is "ai_summary" (top-level)
        if (stats.ai_summary && (stats.ai_summary.zh || stats.ai_summary.en)) {
          console.log("Using Agent Analysis (DeepSeek)");
          const summary = language === 'zh' ? stats.ai_summary.zh : stats.ai_summary.en;
          setAnalysisText(summary);
          return;
        }

        // Fallback: Construct summary from available raw paragraphs
        let parts = [];
        if (stats.macro?.fed_futures?.trend) {
          const fedText = language === 'zh' ? `美联储趋势: ${stats.macro.fed_futures.trend}` : `Fed Trend: ${stats.macro.fed_futures.trend}`;
          parts.push(fedText);
        }
        if (stats.daily_report?.stablecoins?.paragraph) {
          parts.push(stats.daily_report.stablecoins.paragraph);
        }

        if (parts.length > 0) {
          setAnalysisText(parts.join("\n\n"));
        } else {
          setAnalysisText(t.marketAnalysis.content);
        }
      } catch (e) {
        console.error("Failed to load analysis", e);
        setAnalysisText(t.marketAnalysis.content);
      }
    }
    loadAnalysis();
  }, [t, language]);

  // Helper to render formatted text (Markdown-like)
  const renderFormattedText = (text: string) => {
    if (!text) return null;

    // Split into paragraphs/lines
    const lines = text.split('\n');

    return lines.map((line, lineIndex) => {
      if (!line.trim()) return <br key={lineIndex} />;

      // Handle bullets
      let cleanLine = line;
      if (cleanLine.trim().startsWith('* ') || cleanLine.trim().startsWith('- ')) {
        cleanLine = '• ' + cleanLine.trim().substring(2);
      }

      // Parse bold **text**
      const parts = cleanLine.split(/(\*\*.*?\*\*)/g);

      return (
        <div key={lineIndex} className="min-h-[1.5em] mb-1">
          {parts.map((part, idx) => {
            if (part.startsWith('**') && part.endsWith('**')) {
              const content = part.substring(2, part.length - 2);
              return (
                <span key={idx} className="font-bold text-[#E8E8E8] shadow-sm">
                  {content}
                </span>
              );
            }
            return <span key={idx}>{part}</span>;
          })}
        </div>
      );
    });
  };

  const contentToDisplay = analysisText || t.marketAnalysis.content;

  // Check if content is long (more than 200 characters)
  const isLongContent = contentToDisplay.length > 500; // Increased limit for better view
  const displayContent = isExpanded || !isLongContent
    ? contentToDisplay
    : contentToDisplay.slice(0, 500) + '...';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="bg-[#1a1a1a] border border-[#2D3139] p-6 my-6 rounded-sm shadow-lg"
    >
      <div className="flex items-center justify-between mb-4 border-b border-[#2D3139] pb-3">
        <h3 className="text-base font-mono font-medium text-[#39FF14] tracking-wide flex items-center gap-2" style={{ textShadow: '0 0 8px rgba(57, 255, 20, 0.4)' }}>
          <span>🤖</span> {t.marketAnalysis.title}
        </h3>
        <span className="text-xs font-mono text-[#8E9297]">
          {t.marketAnalysis.updateTime}: {updateTime}
        </span>
      </div>

      <div className="text-sm font-sans text-[#B0B3B8] leading-relaxed">
        {renderFormattedText(displayContent)}
      </div>

      {isLongContent && (
        <div className="text-right border-t border-[#2D3139] mt-3 pt-2">
          <motion.button
            onClick={() => setIsExpanded(!isExpanded)}
            className="inline-flex items-center gap-2 text-xs font-mono text-[#39FF14] hover:text-[#39FF14] transition-colors group"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <span>{isExpanded ? t.marketAnalysis.collapse : t.marketAnalysis.expand}</span>
            {isExpanded ? (
              <ChevronUp className="w-4 h-4 group-hover:translate-y-[-2px] transition-transform" />
            ) : (
              <ChevronDown className="w-4 h-4 group-hover:translate-y-[2px] transition-transform" />
            )}
          </motion.button>
        </div>
      )}
    </motion.div>
  );
}