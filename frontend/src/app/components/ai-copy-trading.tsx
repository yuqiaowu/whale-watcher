import { motion, AnimatePresence } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";
import { useState } from "react";
import {
  TrendingUp,
  Activity,
} from "lucide-react";
import { ProfitCurve } from "./profit-curve";


type Tab = 'current' | 'history' | 'decisions';

import { useEffect } from "react";
import {
  fetchSummary,
  fetchPositions,
  fetchHistory,
  fetchAgentDecision,
  type PortfolioSummary,
  type Position,
  type TradeHistory,
  type AgentDecision
} from "@/lib/api";

export function AICopyTrading() {
  const { t, language } = useLanguage();
  const [activeTab, setActiveTab] = useState<Tab>('current');

  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [history, setHistory] = useState<TradeHistory[]>([]);
  const [decisions, setDecisions] = useState<AgentDecision[]>([]);


  useEffect(() => {
    async function loadData() {
      console.log("AICopyTrading: loading data...");
      try {
        // Run in parallel
        const [sumData, posData, histData, decData] = await Promise.all([
          fetchSummary().catch(e => { console.error("fetchSummary failed", e); return null; }),
          fetchPositions().catch(e => { console.error("fetchPositions failed", e); return []; }),
          fetchHistory().catch(e => { console.error("fetchHistory failed", e); return []; }),
          fetchAgentDecision().catch(e => { console.error("fetchAgentDecision failed", e); return []; })
        ]);

        console.log("AICopyTrading: Data received", { sumData, posCount: Array.isArray(posData) ? posData.length : 0 });

        if (sumData) setSummary(sumData);
        if (Array.isArray(posData)) setPositions(posData);
        if (Array.isArray(histData)) setHistory(histData);
        if (Array.isArray(decData)) setDecisions(decData);
      } catch (e) {
        console.error("Failed to fetch data", e);
      }
    }

    loadData();
    const interval = setInterval(loadData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);




  return (
    <div className="flex-1 flex flex-col gap-4 text-[#E8E8E8] min-h-0">
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-0">
        {/* Left Column - Profit Curve (6 cols) */}
        <div className="lg:col-span-6 flex flex-col min-h-0 bg-[#111418] border border-[#2D3139]/50 rounded-sm p-4 overflow-hidden">
          <div className="flex items-center gap-2 mb-4 flex-shrink-0">
            <Activity className="w-4 h-4 text-[#39FF14]" />
            <h3 className="text-sm font-bold tracking-wide">{t.aiTrading.profitCurve}</h3>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-6 flex-shrink-0">
            <div className="bg-[#0A0C0E] border border-[#2D3139]/30 p-4">
              <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.initialValue}</div>
              <div className="text-xl font-bold font-mono">${summary?.initialNav?.toLocaleString() ?? "10,000"}</div>
            </div>
            <div className="bg-[#0A0C0E] border border-[#2D3139]/30 p-4">
              <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.currentValue}</div>
              <div className="text-xl font-bold font-mono">
                ${summary?.nav?.toLocaleString() ?? "---"}
              </div>
            </div>
            <div className="bg-[#0A0C0E] border border-[#2D3139]/30 p-4">
              <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.historyStats.totalProfitLoss}</div>
              <div className={`text-xl font-bold font-mono flex items-center gap-1 ${summary?.totalPnl && summary.totalPnl >= 0 ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                <TrendingUp className="w-4 h-4" />
                {summary?.pnlPercent ? (summary.pnlPercent > 0 ? '+' : '') + summary.pnlPercent + '%' : '---'}
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0">
            <ProfitCurve />
          </div>
        </div>
        {/* Right Column - Tabs & Content (6 cols) */}
        <div className="lg:col-span-6 bg-[#111418] border border-[#2D3139]/50 rounded-sm overflow-hidden flex flex-col min-h-0">
          <div className="flex border-b border-[#2D3139]/50 flex-shrink-0">
            {(['current', 'history', 'decisions'] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 py-4 text-sm font-bold tracking-widest relative transition-colors ${activeTab === tab ? "text-[#39FF14]" : "text-[#8E9297] hover:text-[#E8E8E8]"}`}
              >
                {t?.aiTrading?.tabs?.[tab] || tab.toUpperCase()}
                {activeTab === tab && (
                  <motion.div
                    layoutId="tabUnderline"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#39FF14] shadow-[0_0_10px_#39FF14]"
                  />
                )}
              </button>
            ))}
          </div>

          <div className="flex-1 p-4 overflow-y-auto scrollbar-hide">
            <AnimatePresence mode="wait">
              {activeTab === 'current' && (
                <motion.div
                  key="current"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="space-y-6"
                >
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-[#0A0C0E] border border-[#2D3139]/30 p-4">
                      <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.positionProfitLoss}</div>
                      <div className={`text-2xl font-bold font-mono ${positions.reduce((acc, p) => acc + (p.pnl || 0), 0) >= 0 ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                        ${positions.reduce((acc, p) => acc + (p.pnl || 0), 0).toFixed(2)}
                      </div>
                    </div>
                    <div className="bg-[#0A0C0E] border border-[#2D3139]/30 p-4">
                      <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.cashBalance}</div>
                      <div className="text-2xl font-bold font-mono text-[#E8E8E8]">
                        ${(summary?.nav ? summary.nav - positions.reduce((acc, p) => acc + (p.entryPrice * Number(p.amount) / (p.leverage || 1)), 0) : 0).toFixed(2)}
                      </div>
                    </div>
                  </div>

                  {positions.length === 0 ? (
                    <div className="text-center py-10 text-[#8E9297] bg-[#0A0C0E] border border-[#2D3139]/30 rounded-sm">
                      {t.aiTrading.noPositions}
                    </div>
                  ) : (
                    positions.map((pos, idx) => (
                      <div key={`${pos.symbol || 'unknown'}-${idx}`} className="bg-[#0A0C0E] border border-[#2D3139]/30 rounded-sm p-5 space-y-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="font-bold">
                              <span className="text-base">{pos.symbol || 'Unknown'}</span>
                              <span className="text-xs text-[#8E9297] ml-2">{pos.name || ''}</span>
                            </div>
                          </div>
                          <div className={`text-[10px] px-2 py-0.5 border rounded ${pos.type === 'long' ? 'bg-[#39FF14]/10 text-[#39FF14] border-[#39FF14]/30' : 'bg-[#FF3131]/10 text-[#FF3131] border-[#FF3131]/30'}`}>
                            {pos.leverage}x {(pos.type || '').toUpperCase()}
                          </div>
                        </div>

                        <div className="text-[10px] text-[#8E9297] font-mono">
                          {t.aiTrading.holding}: {pos.amount}
                        </div>

                        <div className="grid grid-cols-2 gap-y-4">
                          <div>
                            <div className="text-[10px] text-[#8E9297] mb-1">{t.aiTrading.openPrice}</div>
                            <div className="font-mono text-sm">${pos.entryPrice?.toLocaleString() ?? '---'}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-[#8E9297] mb-1">{t.aiTrading.currentPrice}</div>
                            <div className="font-mono text-sm">${pos.currentPrice?.toLocaleString() ?? '---'}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-[#FF3131] mb-1">○ {t.aiTrading.stopLoss}</div>
                            <div className="font-mono text-sm text-[#FF3131]">${pos.stopLoss?.toLocaleString() ?? '---'}</div>
                          </div>
                          <div>
                            <div className="text-[10px] text-[#39FF14] mb-1">◎ {t.aiTrading.takeProfit}</div>
                            <div className="font-mono text-sm text-[#39FF14]">${pos.takeProfit?.toLocaleString() ?? '---'}</div>
                          </div>
                        </div>

                        <div className="pt-4 border-t border-[#2D3139]/30 flex items-center justify-between">
                          <div className="text-[10px] text-[#8E9297]">{t.aiTrading.profitLoss}</div>
                          <div className="flex items-center gap-2">
                            <span className={`font-mono text-sm font-bold ${pos.pnl >= 0 ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                              ${(pos.pnl || 0).toFixed(2)}
                            </span>
                            <span className={`text-[10px] font-mono px-1 rounded ${pos.pnl >= 0 ? 'bg-[#39FF14]/10 text-[#39FF14]' : 'bg-[#FF3131]/10 text-[#FF3131]'}`}>
                              {(pos.pnlPercent || 0).toFixed(2)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </motion.div>
              )}
              {activeTab === 'history' && (
                <motion.div
                  key="history"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="space-y-6"
                >
                  {/* Summary Stats */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-[#111418] border border-[#2D3139] p-3 rounded-sm">
                      <div className="text-[10px] text-[#8E9297] mb-1">{t.aiTrading.historyStats.totalProfitLoss}</div>
                      <div className={`text-xl font-bold font-mono ${summary?.totalPnl && summary.totalPnl >= 0 ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                        {summary?.totalPnl ? (summary.totalPnl > 0 ? '+' : '') + summary.totalPnl.toFixed(0) : '---'}
                      </div>
                    </div>
                    <div className="bg-[#111418] border border-[#2D3139] p-3 rounded-sm">
                      <div className="text-[10px] text-[#8E9297] mb-1">{t.aiTrading.historyStats.winRate}</div>
                      <div className="text-xl font-bold font-mono text-[#39FF14]">{summary?.winRate ?? "--"}%</div>
                    </div>
                    <div className="bg-[#111418] border border-[#2D3139] p-3 rounded-sm">
                      <div className="text-[10px] text-[#8E9297] mb-1">{t.aiTrading.historyStats.tradeCount}</div>
                      <div className="text-xl font-bold font-mono text-[#E8E8E8]">{history.length}</div>
                    </div>
                  </div>

                  {/* Trade List */}
                  <div className="space-y-3">
                    {history.length === 0 ? (
                      <div className="text-center py-10 text-[#8E9297] bg-[#0A0C0E] border border-[#2D3139]/30 rounded-sm">
                        {t.aiTrading.noHistory}
                      </div>
                    ) : (
                      history.map((trade, i) => (
                        <div key={trade.id || i} className="bg-[#111418] border border-[#2D3139] rounded-sm p-4">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <span className="text-base font-bold text-white">{trade.symbol}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${trade.type?.toLowerCase().includes('long') ? 'bg-[#1E3A8A]/30 text-[#60A5FA] border-[#1E3A8A]/50' : 'bg-[#450A0A]/30 text-[#FF3131] border-[#450A0A]/50'}`}>
                                {(trade.type || '').toUpperCase()}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`text-sm font-bold font-mono ${(trade.pnl || 0) >= 0 ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                                {(trade.pnl || 0) >= 0 ? '+' : ''}${(trade.pnl || 0).toFixed(2)}
                              </span>
                              <span className={`text-[10px] px-1 py-0.5 rounded border ${(trade.pnl || 0) >= 0 ? 'bg-[#14532D]/30 text-[#39FF14] border-[#14532D]/50' : 'bg-[#450A0A]/30 text-[#FF3131] border-[#450A0A]/50'}`}>
                                {(trade.pnlPercent || 0).toFixed(2)}%
                              </span>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-y-3 mb-3">
                            <div>
                              <div className="text-[10px] text-[#8E9297]">{t.aiTrading.entryLabel}: <span className="text-[#E8E8E8] font-mono">${trade.entryPrice?.toLocaleString() ?? '---'}</span></div>
                            </div>
                            <div>
                              <div className="text-[10px] text-[#8E9297]">{t.aiTrading.exitLabel}: <span className="text-[#E8E8E8] font-mono">${trade.exitPrice?.toLocaleString() ?? '---'}</span></div>
                            </div>
                            <div>
                              <div className="text-[10px] text-[#8E9297]">{t.aiTrading.quantity}: <span className="text-[#E8E8E8] font-mono">{trade.amount}</span></div>
                            </div>
                            <div>
                              <div className="text-[10px] text-[#8E9297]">{t.aiTrading.leverage}: <span className="text-[#60A5FA] font-mono">{trade.leverage}x</span></div>
                            </div>
                          </div>
                          <div className="pt-3 border-t border-[#2D3139]/30 text-[10px] text-[#5A5E66] font-mono">
                            {trade.entryTime} - {trade.exitTime}
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                </motion.div>

              )}

              {activeTab === 'decisions' && (
                <motion.div
                  key="decisions"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="space-y-8"
                >
                  {decisions.length === 0 ? (
                    <div className="text-xs text-[#8E9297]">Loading analysis...</div>
                  ) : (
                    decisions.map((decision, idx) => (
                      <div key={idx} className="border-b border-[#2D3139]/50 pb-8 last:border-0 last:pb-0">
                        {/* Decision Header with Timestamp */}
                        <div className="flex items-center gap-2 mb-4">
                          <div className="text-xs font-mono text-[#8E9297] bg-[#1A1D24] px-2 py-1 rounded border border-[#2D3139]">
                            Timestamp: {decision.timestamp || 'Unknown'}
                          </div>
                        </div>

                        {/* Market Analysis */}
                        <div className="mb-6">
                          <div className="flex items-center gap-2 mb-3">
                            <div className="w-1 h-3 bg-gradient-to-b from-[#3B82F6] to-[#60A5FA] rounded-full"></div>
                            <h3 className="text-sm font-bold text-white">{t.aiTrading.marketAnalysis}</h3>
                          </div>
                          <div className="bg-[#111418] border border-[#2D3139] p-4 rounded-sm text-xs leading-relaxed text-[#B0B3B8] space-y-3 font-sans whitespace-pre-line">
                            {decision.analysis_summary?.[language as 'zh' | 'en'] || decision.analysis_summary?.['en'] || "No analysis"}
                          </div>
                        </div>

                        {/* Context Analysis (New Section) */}
                        {decision.context_analysis && (
                          <div className="mb-8">
                            <div className="flex items-center gap-2 mb-3">
                              <div className="w-1 h-3 bg-gradient-to-b from-[#8B5CF6] to-[#A78BFA] rounded-full"></div>
                              <h3 className="text-sm font-bold text-white">{t.aiTrading.decisionDetail}</h3>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#3B82F6] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#3B82F6] rounded-full"></div>
                                  Technical Signal
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed">
                                  {decision.context_analysis.technical_signal?.[language as 'zh' | 'en'] || decision.context_analysis.technical_signal?.['en'] || "N/A"}
                                </div>
                              </div>
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#8B5CF6] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#8B5CF6] rounded-full"></div>
                                  Macro & On-Chain
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed">
                                  {decision.context_analysis.macro_onchain?.[language as 'zh' | 'en'] || decision.context_analysis.macro_onchain?.['en'] || "N/A"}
                                </div>
                              </div>
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#06B6D4] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#06B6D4] rounded-full"></div>
                                  Quantitative (Qlib/Z-Vol)
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed">
                                  {decision.context_analysis.quantitative_analysis?.[language as 'zh' | 'en'] || decision.context_analysis.quantitative_analysis?.['en'] || "Evaluating quant markers..."}
                                </div>
                              </div>
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#F97316] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#F97316] rounded-full"></div>
                                  Regime Safety (Knife/Rocket)
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed">
                                  {decision.context_analysis.regime_safety?.[language as 'zh' | 'en'] || decision.context_analysis.regime_safety?.['en'] || "Analyzing trend exhaustion..."}
                                </div>
                              </div>
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#39FF14] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#39FF14] rounded-full"></div>
                                  Portfolio Status
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed">
                                  {decision.context_analysis.portfolio_status?.[language as 'zh' | 'en'] || decision.context_analysis.portfolio_status?.['en'] || "N/A"}
                                </div>
                              </div>
                              <div className="bg-[#1A1D24] border border-[#2D3139]/50 p-3 rounded-sm space-y-1">
                                <div className="text-[10px] text-[#FCD34D] font-bold uppercase tracking-wider flex items-center gap-1">
                                  <div className="w-1 h-3 bg-[#FCD34D] rounded-full"></div>
                                  Reflection
                                </div>
                                <div className="text-xs text-[#d1d5db] leading-relaxed italic">
                                  "{decision.context_analysis.reflection?.[language as 'zh' | 'en'] || decision.context_analysis.reflection?.['en'] || "No reflection"}"
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Execution Actions */}
                        <div>
                          <div className="flex items-center gap-2 mb-3">
                            <div className="w-1 h-3 bg-gradient-to-b from-[#E9B124] to-[#FCD34D] rounded-full"></div>
                            <h3 className="text-sm font-bold text-white">{t.aiTrading.actions} {decision.actions ? `(${decision.actions.length})` : ''}</h3>
                          </div>
                          <div className="space-y-3">
                            {(!decision.actions || decision.actions.length === 0) ? (
                              <div className="bg-[#111418] border border-[#2D3139] rounded-sm p-4">
                                <div className="flex items-center gap-2 mb-2">
                                  <span className="text-base font-bold text-white">PORTFOLIO</span>
                                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-[#2D3139] bg-[#1A1D24] text-[#8E9297]">
                                    {t.aiTrading.hold}
                                  </span>
                                </div>
                                <div className="text-xs text-[#B0B3B8] leading-relaxed">
                                  {decision.context_analysis?.portfolio_status?.[language as 'zh' | 'en'] ||
                                    decision.context_analysis?.portfolio_status?.['en'] ||
                                    decision.analysis_summary?.[language as 'zh' | 'en'] ||
                                    "当前市场情绪不明确或触及风控限制，模型决定暂不开仓，继续保持观望状态。"}
                                </div>
                              </div>
                            ) : (
                              decision.actions.map((action, i) => (
                                <div key={`${idx}-${i}`} className={`bg-[#111418] border rounded-sm p-4 ${action.action === 'REJECTED' ? 'border-red-500/20 bg-red-900/5' : 'border-[#2D3139]'}`}>
                                  <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                      <span className="text-base font-bold text-white">{action.symbol}</span>
                                      <span className={`text-[10px] px-1.5 py-0.5 rounded border border-[#4B5563]/30 ${action.action === 'REJECTED' ? 'bg-red-500/20 text-red-500' : 'bg-[#2D3139] text-[#8E9297]'}`}>
                                        {action.action}
                                      </span>
                                    </div>
                                  </div>
                                  <div className="text-[10px] text-[#8E9297] mb-2">{t.aiTrading.logicLabel}</div>
                                  <div className="mb-4 text-xs text-[#B0B3B8] leading-relaxed">
                                    {action.entry_reason?.[language as 'zh' | 'en'] || action.entry_reason?.['en'] || "No reason"}
                                  </div>
                                  {action.exit_plan && (
                                    <div className="flex items-center justify-between pt-3 border-t border-[#2D3139]/30">
                                      <div className="flex items-center gap-2">
                                        <span className="text-[10px] text-[#5A5E66]">{t.aiTrading.takeProfit}:</span>
                                        <span className="text-sm font-bold font-mono text-[#39FF14]">{action.exit_plan.take_profit ?? '---'}</span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <span className="text-[10px] text-[#5A5E66]">{t.aiTrading.stopLoss}:</span>
                                        <span className="text-sm font-bold font-mono text-[#FF3131]">{action.exit_plan.stop_loss ?? '---'}</span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div >
      </div >
    </div >
  );
}
