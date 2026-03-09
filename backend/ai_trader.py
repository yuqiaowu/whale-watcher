"""
DeepSeek Trading Agent (Dolores) - Whale Enhanced Edition
Integrates Qlib Multi-Coin Model, MARKET REALITY (Whale Flow + Liquidation), and LLM Reasoning.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from openai import OpenAI
import time
from okx_executor import OKXExecutor
from notifier import notify_trade_execution # Restored Notification System

# Load environment variables
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Client
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL)

# Paths
# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "frontend" / "data"

QLIB_DATA_DIR = BASE_DIR / "qlib_data"
PAYLOAD_PATH = QLIB_DATA_DIR / "deepseek_payload.json"

# Centralized Data Paths (Frontend Accessible)
PORTFOLIO_PATH = DATA_DIR / "portfolio_state.json"
TRADE_HISTORY_PATH = DATA_DIR / "trade_history.json"
AGENT_LOG_PATH = DATA_DIR / "agent_decision_log.json"
AGENT_MEMORY_PATH = DATA_DIR / "agent_memory.json"

class TradeMemory:
    """
    Manages the recording of trade rationale and outcomes for AI reflection.
    """
    def __init__(self):
        if not AGENT_MEMORY_PATH.exists():
            with open(AGENT_MEMORY_PATH, "w") as f:
                json.dump([], f)
    
    def log_trade(self, symbol, action, size, reason, market_snapshot):
        """
        Log a new trade with full context.
        market_snapshot: dict containing current price, rsi, adx, whale_flow etc.
        """
        try:
            with open(AGENT_MEMORY_PATH, "r") as f:
                history = json.load(f)
            
            entry = {
                "id": f"{symbol}_{int(datetime.now().timestamp())}",
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "action": action,
                "entry_price": market_snapshot.get('price', 0),
                "leverage": 1, # Default
                "reason": reason,
                "context": {
                    "rsi": market_snapshot.get('rsi_14', '?'),
                    "adx": market_snapshot.get('adx_14', '?'),
                    "whale_flow": market_snapshot.get('whale_flow', '?'),
                    "funding_rate": market_snapshot.get('funding_rate', '?'),
                    "bb_width": market_snapshot.get('bb_width_pct', '?'),
                    "bb_trend": market_snapshot.get('bb_trend', '?')
                },
                "outcome": "Closed" if "close" in action.lower() else None
            }
            
            history.append(entry)
            # Keep last 50 trades
            if len(history) > 50: history = history[-50:]
                
            with open(AGENT_MEMORY_PATH, "w") as f:
                json.dump(history, f, indent=2)
            print(f"🧠 Logged trade memory for {symbol}")
            
        except Exception as e:
            print(f"⚠️ Failed to log trade memory: {e}")

    def get_recent_performance(self):
        """
        Returns a rich summary of recent trades to inject into AI prompt for self-reflection.
        Includes full rationale, market context at entry, outcome, and the LATEST cycle reflection.
        """
        summary = "=== 📜 RECENT TRADE MEMORY (SELF-REFLECTION — LEARN FROM THIS) ===\n"
        summary += "Critically review these past decisions before acting:\n\n"
        
        # 1. Get the absolute latest thought/reflection from the DB (even if HOLD/WAIT)
        try:
            from db_client import db
            history_db = db.get_data("agent_decision_log", [])
            if history_db and isinstance(history_db, list) and len(history_db) > 0:
                latest_decision = history_db[0]
                latest_time = latest_decision.get("timestamp", "Unknown Time")
                reflection = latest_decision.get("context_analysis", {}).get("reflection", {}).get("en", "")
                if reflection:
                    summary += f"[LATEST AI CYCLE: {latest_time}]\n"
                    summary += f"Your Previous Reflection: {reflection}\n\n"
        except Exception as e:
            pass  # Silently skip if DB fails to load
            
        # 2. Get Real Trade Outcomes (PnL) from executed history
        recent_pnls = {}
        if TRADE_HISTORY_PATH.exists():
            try:
                with open(TRADE_HISTORY_PATH, "r") as f:
                    th = json.load(f)
                    for t in th[-30:]: # scan recent history
                        sym = t.get('symbol')
                        action = t.get('action', '')
                        if "Close" in action or "Reduce" in action:
                            pnl = t.get('pnl', 0)
                            pnl_pct = t.get('pnlPercent', 0)
                            if sym not in recent_pnls:
                                recent_pnls[sym] = []
                            res_str = f"赢利" if pnl > 0 else f"亏损"
                            recent_pnls[sym].append(f"✅ {res_str}: ${pnl} ({pnl_pct}%)")
            except Exception:
                pass
                
        # 3. Get executed trades via AGENT_MEMORY_PATH
        if AGENT_MEMORY_PATH.exists():
            try:
                with open(AGENT_MEMORY_PATH, "r") as f:
                    trade_hist = json.load(f)
                if trade_hist and isinstance(trade_hist, list):
                    recent = trade_hist[-5:]
                    for i, t in enumerate(recent, 1):
                        ts = t['timestamp'][:16]
                        sym = t['symbol']
                        act = t['action']
                        price = t.get('entry_price', '?')
                        
                        rationale_en = t['reason'].get('en', '') if isinstance(t.get('reason'), dict) else str(t.get('reason', ''))
                        ctx = t.get('context', {})
                        rsi = ctx.get('rsi', '?')
                        adx = ctx.get('adx', '?')
                        whale = ctx.get('whale_flow', '?')
                        fund = ctx.get('funding_rate', '?')
                        bb = f"{ctx.get('bb_width', '?')}% ({ctx.get('bb_trend', '?')})"
                        
                        summary += f"[TRADE {i}] {ts} | {act} {sym} @ ${price}\n"
                        summary += f"    Market at entry: RSI={rsi}, ADX={adx}, WhaleFlow={whale}, Funding={fund}, BB={bb}\n"
                        
                        # Inject PnL if we found any recent close for this symbol
                        if sym in recent_pnls and len(recent_pnls[sym]) > 0:
                            # Pop the oldest matching PNL from recent queue to pair it
                            pnl_outcome = recent_pnls[sym].pop(0)
                            summary += f"    Result Context: {pnl_outcome} shortly after this.\n"
                            
                        summary += f"    Rationale: {rationale_en[:400]}\n\n"
            except Exception as e:
                pass
                
        summary += "⚠️ REFLECTION MANDATE: Before ANY new action, explicitly state what you learned from the above history and how it affects this decision.\n"
        return summary

memory = TradeMemory()
WHALE_DATA_PATH = BASE_DIR.parent / "frontend/data/whale_analysis.json" # [NEW]

# ------------------------------------------------------------------------
# 1. System Prompt (Optimized for Whale Integration)
# ------------------------------------------------------------------------
SYSTEM_PROMPT = """
🟩 0. YOU ARE “AI TRADING AGENT – DOLORES”

Role: Professional Crypto Trading AI.
Capabilities:
- Analyze Multi-Coin Market Structure (Price, Volume, Trend).
- Interpret Sentiment Data (Funding Rate, Open Interest, Z-Scores).
- **INTEGRATE WHALE INSIGHTS**: Process Token Flow, Stablecoin Flow, and Liquidation Pain.
- Detect Pain Trades (Squeezes, Crowded Trades) using On-Chain evidence.
- Manage Risk (Position Sizing, Stop Loss, Portfolio Heat).

Goal: Achieve stable risk-adjusted returns. Avoid ruin. Catch "Whale Traps".

🟧 1. CURRENT TIME
Current Timestamp: {{CURRENT_TIMESTAMP}}

🟦 2. MARKET INPUTS (QLIB + SENTIMENT)
You will receive a JSON payload containing:
- `qlib_score`: Relative strength prediction (Higher = Stronger).
- `rank`: 1 (Best) to 5 (Worst).
- `market_data`: 
    - **Technical**: RSI (14), MACD Hist, ATR, Bollinger Width, Momentum.
    - **Sentiment**: Funding Rate, Funding Z-Score, OI Change, OI RSI.
    - **Correlation**: BTC Correlation (btc_corr_24h).
    - **Volatility**: Normalized ATR (natr_14).

{{QLIB_JSON_PAYLOAD}}

🟪 2.2 WHALE & LIQUIDATION REALITY
This data comes from direct on-chain monitoring and exchange liquidation feeds.

{{WHALE_CONTEXT}}


🟦 2.1 MACRO TREND (1D TIMEFRAME)
Use this daily context to filter 4H signals.
- **Trend**: Price vs SMA50 (Bullish if Price > SMA50).
- **Structure**: Recent Highs/Lows.

{{DAILY_CONTEXT}}

🟪 2.3 MARKET ENVIRONMENT
{{DAILY_CONTEXT}}

🟨 3. NEWS & ON-CHAIN CONTEXT (OPTIONAL)
{{NEWS_CONTEXT}}

🟥 4. ANALYSIS & HYPOTHESIS
Use the provided data to detect market traps and identify your trading hypothesis.

HYPOTHESIS OPTIONS:
1. **TREND_FOLLOWING**: Ride the momentum based on flow and technicals.
2. **MEAN_REVERSION**: Trade reversals when price and data reach extremes.
3. **MICROSTRUCTURE_SQUEEZE**: Capitalize on liquidity traps and funding anomalies.
4. **NARRATIVE_DIVERGENCE**: When data contradicts price action (e.g., Hidden Accumulation).
5. **WHALE_FRONT_RUN**: Align with institutional flow.

🟧 5. PORTFOLIO & RISK MANAGEMENT
Current State:
{{PORTFOLIO_STATE_JSON}}

**🟥 5. THE PRIMARY MISSION: ACTIVE POSITION MAINTENANCE (MANDATORY FIRST)**
Before even thinking about new trades, you MUST address your current exposure.
1. **THE 1:1 CLEANSE RULE (MANDATORY)**: Every decision cycle, your first task is a per-asset audit.
   - **MAPPING REQUIREMENT**: For EVERY symbol listed in `{{PORTFOLIO_STATE_JSON}}`, you **MUST** provide a corresponding entry in the `actions` array. 
   - **ZERO OMISSION**: You are NOT allowed to skip any current holding. If you hold BTC, DOGE, BNB, or any other asset, it MUST be listed.
   - **ASSET-SPECIFIC DEFENSE**: 
     - For coins WITH whale data (ETH, SOL): Defend based on Flow + Technicals.
     - For coins WITHOUT whale data (BTC, DOGE, BNB): You **MUST** defend the position based on Technicals (RSI/ADX) + Liquidation Pain + Qlib Ranking. 
     - "Missing data" is NOT a reason to skip an action.
   - **ZERO TOLERANCE**: Failing to provide a matching action entry for ANY symbol in portfolio is a **LOGICAL INTEGRITY BREACH**.

2. **THE SECONDARY MISSION: NEW ENTRIES (PRIVILEGED ACCESS)**:
   - Opening a new position is a **REWARD** for having a healthy, logically-aligned portfolio.
   - If you have conflicts in your current positions that you aren't fixing, do NOT open new ones.
   - All new entries MUST follow the Hypothesis Playbooks (Section 4C).


Market Regime: {{MARKET_REGIME}}
Dynamic Exposure Limits (STRICT):
- Max Total LONG Exposure: ${{MAX_LONG_LIMIT_USD}} ({{MAX_LONG_PCT}}% of Equity)
- Max Total SHORT Exposure: ${{MAX_SHORT_LIMIT_USD}} ({{MAX_SHORT_PCT}}% of Equity)
- Current LONG Exposure: ${{CURR_LONG_EXP_USD}}
- Current SHORT Exposure: ${{CURR_SHORT_EXP_USD}}
- Available LONG Room: ${{AVAILABLE_LONG_USD}}
- Available SHORT Room: ${{AVAILABLE_SHORT_USD}}

Constraints:
- Max Open Positions: 3.
- Max Risk Per Trade: 2% of NAV.
- Max Leverage: 5x (Normal), 10x (High Conviction Whale Signal).
- **DO NOT exceed the Available Room.** 
- **SAFETY RULE**: Always keep your total exposure at least $10 BELOW the limit to account for market volatility and fees.
- If available room is low, consider closing existing positions first.

🟫 6. OUTPUT FORMAT (JSON ONLY)
Structure:
{
  "analysis_summary": {
    "zh": "必须是中文，按以下结构分段阐述：\n1. **【叙事校验】**：判断当前驱动力是Impulse还是已定价，识别市场主旋律。\n2. **【决策依据详情】**：综合 Technical Signal, Macro & On-Chain, Quantitative (Qlib/Z-Vol) 的交叉验证。\n3. **【痛苦交易】**：分析爆仓燃料与 L/S Ratio，识别是否处于‘踩踏’或‘衰竭’阶段。\n4. **【剧本选择】**：明确 4C 中的剧本（WHALE_FRONT_RUN 等）及选择理由。",
    "en": "Must be in English, structured as follows:\n1. **[Narrative Validation]**: Impulse vs Priced-in.\n2. **[Decision Details]**: Cross-verification of Tech, Whale, and Quant signals.\n3. **[Pain Trade]**: Liquidation fuel and L/S Ratio analysis.\n4. **[Scenario Selection]**: Chosen Scenario (4C) and justification."
  },
  "hypothesis_scenario": "TREND_FOLLOWING | MEAN_REVERSION | MICROSTRUCTURE_SQUEEZE | NARRATIVE_DIVERGENCE | WHALE_FRONT_RUN",
  "contrary_signal_check": {
    "zh": "列出当前最严重的冲突数据或风险点，并解释为什么忽略/对冲它。",
    "en": "List the most significant contrary signal or risk point and justify why it doesn't invalidate the trade."
  },
  "context_analysis": {
    "technical_signal": { "zh": "技术面概括 (RSI, ADX...)", "en": "Brief technical summary." },
    "macro_onchain": { "zh": "鲸鱼数据与资金费率分析", "en": "Whale flow & funding analysis." },
    "quantitative_analysis": { 
        "zh": "分析 Qlib 排名靠前的币种及 Z-Score 的异常显著性（如成交量或资金费率的统计偏差）。", 
        "en": "Analyze Qlib top-ranked coins and Z-Score significance (statistical deviations in vol/funding)." 
    },
    "regime_safety": { 
        "zh": "【必填】基于Section 4E评估: 1)当前RSI/ADX/NATR状态; 2)上下影线比率; 3)多空爆仓比; 4)鲸鱼净流向。最终给出明确判断: KNIFE(接飞刀)/ROCKET(挡火箭)/SAFE_MR(安全均值回归)/WHALE_SQUEEZE(鲸鱼轧空)/WHALE_ACCUMULATION(鲸鱼托底)", 
        "en": "【Required】Based on Section 4E: 1) RSI/ADX/NATR current state; 2) Upper/Lower Wick Ratio; 3) Liquidation long/short ratio; 4) Whale net flow direction. Conclude with explicit verdict: KNIFE / ROCKET / SAFE_MR / WHALE_SQUEEZE / WHALE_ACCUMULATION and explain why." 
    },
    "portfolio_status": { "zh": "当前持仓风险评估", "en": "Portfolio risk check." }
  },
  "portfolio_management": {
    "ETH": { 
      "action": "hold | adjust_sl_tp | reduce_25 | reduce_50 | reduce_75 | close_position",
      "action_logic": {
        "zh": "针对该具体持仓的独立维护理由（必须结合该币种的鲸鱼流向与技术面偏差）。",
        "en": "Asset-specific maintenance logic (must reference this coin's whale flow and technical divergence)."
      },
      "exit_plan": { "take_profit": 3500, "stop_loss": 2100 } /* Mandatory for adjust_sl_tp */
    },
    ... (one for EACH symbol in mandatory list)
  },
  "new_opportunities": [
    {
      "symbol": "BTC",
      "action": "open_long | open_short | monitor",
      "leverage": 3,
      "position_size_usd": 500,
      "entry_reason": { "zh": "...", "en": "..." },
      "exit_plan": { "take_profit": 120000, "stop_loss": 95000 }
    }
  ]
}

*** LOGIC INTEGRITY RULES ***
1. **MAPPING FORCE**: Your `portfolio_management` object MUST contain keys for exactly these symbols: {{MANDATORY_SYMBOLS_LIST}}.
2. **NO GROUPING**: Provide an independent `action_logic` for EACH key in `portfolio_management`.
"""

# ------------------------------------------------------------------------
# 2. Helper Functions
# ------------------------------------------------------------------------

def get_portfolio_state(executor=None):
    """Load portfolio state from OKX Executor (Real-time) or file (Fallback)."""
    if executor:
        try:
            positions = executor.get_all_positions()
            equity = executor.get_account_equity()
            
            state = {
                "total_equity": equity,
                "cash": equity, # Simplified for prompt
                "positions": []
            }
            
            for p in positions:
                # amount from OKX is contracts usually, calculate value roughly
                # amount * ctVal * price? 
                # OKXExecutor returns 'amount' as pos size.
                try:
                    size = float(p.get("amount", 0))
                    val = size * p.get("currentPrice", 0) # Approx value
                except:
                    size = 0
                    val = 0
                    
                state["positions"].append({
                    "symbol": p["symbol"],
                    "side": p["type"],
                    "entry_price": p.get("entryPrice", 0),
                    "size": size,
                    "value_usd": val,
                    "pnl": p.get("pnl", 0),
                    "leverage": p.get("leverage", 1),
                    "pnlPercent": p.get("pnlPercent", 0) # Use value from executor
                })
            
            # Save this real-time state to file so daily_report.py and frontend can see it
            try:
                # Retain initial_equity and start_time if they exist
                if PORTFOLIO_PATH.exists():
                    try:
                        with open(PORTFOLIO_PATH, "r") as f:
                            old_state = json.load(f)
                        if "initial_equity" in old_state:
                            state["initial_equity"] = old_state["initial_equity"]
                        if "start_time" in old_state:
                            state["start_time"] = old_state["start_time"]
                    except Exception:
                        pass
                
                with open(PORTFOLIO_PATH, "w") as f:
                    json.dump(state, f, indent=2)
                print("✅ Real-time portfolio state saved to file.")
            except Exception as e:
                print(f"⚠️ Failed to save portfolio state: {e}")

            return json.dumps(state, indent=2)
            
        except Exception as e:
            print(f"⚠️ Failed to fetch real portfolio from executor: {e}")
    
    # Fallback to static file
    if PORTFOLIO_PATH.exists():
        with open(PORTFOLIO_PATH, "r") as f:
            return f.read()
    else:
        # Default mock state
        mock_state = {
            "nav": 10000.0,
            "cash": 10000.0,
            "positions": []
        }
        return json.dumps(mock_state, indent=2)

def get_whale_data():
    """Reads the latest whale_analysis.json generated by crypto_brain.py"""
    if not WHALE_DATA_PATH.exists():
        return "No Whale Data Available."
    
    try:
        with open(WHALE_DATA_PATH, "r") as f:
            data = json.load(f)
            
        eth_stat_24h = data.get("eth", {}).get("stats_24h", {})
        eth_stat_7d = data.get("eth", {}).get("stats", {}) # stats is 7d
        
        sol_stat_24h = data.get("sol", {}).get("stats_24h", {})
        sol_stat_7d = data.get("sol", {}).get("stats", {})
        
        btc_stat = data.get("btc", {}).get("stats_24h", {})
        bnb_stat = data.get("bnb", {}).get("stats_24h", {})
        doge_stat = data.get("doge", {}).get("stats_24h", {})
        
        # Extract Liquidation Data (if available)
        eth_liq_long = eth_stat_24h.get("liquidation_long_usd", 0)
        eth_liq_short = eth_stat_24h.get("liquidation_short_usd", 0)
        sol_liq_long = sol_stat_24h.get("liquidation_long_usd", 0)
        sol_liq_short = sol_stat_24h.get("liquidation_short_usd", 0)
        btc_liq_long = btc_stat.get("liquidation_long_usd", 0)
        btc_liq_short = btc_stat.get("liquidation_short_usd", 0)
        bnb_liq_long = bnb_stat.get("liquidation_long_usd", 0)
        bnb_liq_short = bnb_stat.get("liquidation_short_usd", 0)
        doge_liq_long = doge_stat.get("liquidation_long_usd", 0)
        doge_liq_short = doge_stat.get("liquidation_short_usd", 0)
        
        eth_market = data.get("eth", {}).get("market", {})
        sol_market = data.get("sol", {}).get("market", {})
        btc_market = data.get("btc", {}).get("market", {})
        bnb_market = data.get("bnb", {}).get("market", {}) 
        doge_market = data.get("doge", {}).get("market", {})
        
        # Helper to format tech
        def fmt_tech(m):
            if not m: return "No Tech Data"
            
            natr_str = f"Volatility(NATR)={m.get('natr_percent', 0):.2f}%"
            hist = m.get('history_60d', [])
            if len(hist) >= 2:
                curr_natr = hist[-1].get('natr', 0)
                prev_natr = hist[-2].get('natr', 0)
                if curr_natr > prev_natr:
                    natr_str += "[Rising]"
                elif curr_natr < prev_natr:
                    natr_str += "[Falling]"
                else:
                    natr_str += "[Flat]"
                    
            natr_avg = m.get('natr_avg_30d', 0)
            if natr_avg > 0:
                natr_val = m.get('natr_percent', 0)
                if natr_val > natr_avg * 1.1:
                    natr_str += f"(>30d Avg {natr_avg:.2f}%)"
                elif natr_val < natr_avg * 0.9:
                    natr_str += f"(<30d Avg {natr_avg:.2f}%)"
                else:
                    natr_str += f"(~30d Avg {natr_avg:.2f}%)"

            sma50_4h = m.get('sma_50', 0)
            price = m.get('last_closed_close', 0)
            dist_sma50 = ((price - sma50_4h) / sma50_4h * 100) if sma50_4h > 0 else 0
            
            return (f"Last 4H Close=${price:.2f} | 4H SMA50=${sma50_4h:.2f} ({dist_sma50:+.2f}%) | "
                    f"Prev 5 High=${m.get('prev_5_high', 0):.2f} | Prev 5 Low=${m.get('prev_5_low', 0):.2f} | "
                    f"RSI={m.get('rsi_14', 50):.1f} | ADX={m.get('adx_14', 0):.1f} | "
                    f"VolRatio={m.get('vol_ratio_20', 1):.1f}x | VolZ={m.get('vol_zscore_20', 0):.2f} | "
                    f"NATR={m.get('natr_percent', 0):.2f}% | Rank={m.get('price_rank_20', 50):.0f}% | "
                    f"Wick:Up={m.get('upper_wick_ratio',0)*100:.0f}%/Down={m.get('lower_wick_ratio',0)*100:.0f}% | "
                    f"BBW={m.get('bb_width', 0):.3f} | Trend={m.get('bb_trend', 'FLAT')} | Funding={m.get('funding_rate', 0)*100:.4f}% | "
                    f"Stars: Buy={m.get('buy_stars',0)}/Sell={m.get('sell_stars',0)}")

        # Helper: Add directional meaning to token_net_flow for AI clarity.
        # CRITICAL: In our system, positive token_net_flow means tokens flowing INTO exchanges = DISTRIBUTION (Bearish).
        # Negative token_net_flow means tokens flowing OUT of exchanges = ACCUMULATION (Bullish).
        def fmt_token_flow(flow, symbol_name):
            if flow > 0:
                sentiment = "🚨 STRONG_DUMP_THREAT" if flow > 10000 else "📉 BEARISH_FLOW"
                return f"{flow:,.1f} {symbol_name} [TO_EXCHANGE → {sentiment}]"
            elif flow < 0:
                sentiment = "🔥 STRONG_BUY_PRESSURE" if abs(flow) > 10000 else "📈 BULLISH_FLOW"
                return f"{flow:,.1f} {symbol_name} [FROM_EXCHANGE → {sentiment}]"
            else:
                return f"0 {symbol_name} [NEUTRAL]"

        def fmt_stable_flow(flow):
            if flow > 0:
                return f"${flow:,.0f} [STABLECOIN IN → � BULLISH Buy-power entering]"
            elif flow < 0:
                return f"${flow:,.0f} [STABLECOIN OUT → � BEARISH Capital leaving]"
            else:
                return f"$0 [NEUTRAL]"

        # Build Context String
        ctx = "=== ETHEREUM (ETH) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        eth_ls = eth_market.get("whale_ls_ratio", 0)
        eth_pos = eth_market.get("whale_pos_ratio", 0)
        eth_sent = eth_market.get("top_trader_sentiment", 0.5)
        # NOTE: 持仓L/S比 = Who is holding long vs short positions (>1=more longs, <1=more shorts)
        ctx += f"- [持仓L/S比] OKX Whale Account Ratio={eth_ls:.2f} (>1 more longs, <1 more shorts) / Position Size Ratio={eth_pos:.2f}\n"
        ctx += f"- OKX Top Trader Sentiment: {eth_sent:.2f} (Whale Bias: {'Bullish' if eth_sent > 0.5 else 'Bearish' if eth_sent < 0.5 else 'Neutral'})\n"
        ctx += f"- Sentiment Score: 24h={eth_stat_24h.get('sentiment_score', 0):.2f} / 7d={eth_stat_7d.get('sentiment_score', 0):.2f}\n"
        eth_tf_24h = eth_stat_24h.get('token_net_flow', 0)
        eth_tf_7d = eth_stat_7d.get('token_net_flow', 0)
        ctx += f"- Token Net Flow: 24h={fmt_token_flow(eth_tf_24h, 'ETH')} / 7d={fmt_token_flow(eth_tf_7d, 'ETH')}\n"
        eth_sf_24h = eth_stat_24h.get('stablecoin_net_flow', 0)
        eth_sf_7d = eth_stat_7d.get('stablecoin_net_flow', 0)
        ctx += f"- Stablecoin Net Flow: 24h={fmt_stable_flow(eth_sf_24h)} / 7d={fmt_stable_flow(eth_sf_7d)}\n"
        ctx += f"- Technicals: {fmt_tech(eth_market)}\n"
        eth_liq_ratio = eth_liq_long / eth_liq_short if eth_liq_short > 0 else 0
        eth_liq_signal = "⚠️ LONG_FLUSH" if eth_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if eth_liq_short > eth_liq_long * 2 else "BALANCED")
        # NOTE: 爆仓L/S比 = LIQUIDATION ratio (DIFFERENT from 持仓比!). <1 means more SHORTS are being liquidated (short squeeze). >2 means longs are being flushed.
        ctx += f"- [爆仓L/S比 ⚠️DIFFERENT FROM 持仓比] Liquidated Longs ${eth_liq_long:,.0f} / Liquidated Shorts ${eth_liq_short:,.0f} | Liq-Ratio(Long/Short)={eth_liq_ratio:.2f} [{eth_liq_signal}]\n"
        
        ctx += "\n=== SOLANA (SOL) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        sol_ls = sol_market.get("whale_ls_ratio", 0)
        sol_pos = sol_market.get("whale_pos_ratio", 0)
        sol_sent = sol_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX Whale Account Ratio={sol_ls:.2f} (>1 more longs, <1 more shorts) / Position Size Ratio={sol_pos:.2f}\n"
        ctx += f"- OKX Top Trader Sentiment: {sol_sent:.2f} (Whale Bias: {'Bullish' if sol_sent > 0.5 else 'Bearish' if sol_sent < 0.5 else 'Neutral'})\n"
        ctx += f"- Sentiment Score: 24h={sol_stat_24h.get('sentiment_score', 0):.2f} / 7d={sol_stat_7d.get('sentiment_score', 0):.2f}\n"
        sol_tf_24h = sol_stat_24h.get('token_net_flow', 0)
        sol_tf_7d = sol_stat_7d.get('token_net_flow', 0)
        ctx += f"- Token Net Flow: 24h={fmt_token_flow(sol_tf_24h, 'SOL')} / 7d={fmt_token_flow(sol_tf_7d, 'SOL')}\n"
        sol_sf_24h = sol_stat_24h.get('stablecoin_net_flow', 0)
        sol_sf_7d = sol_stat_7d.get('stablecoin_net_flow', 0)
        ctx += f"- Stablecoin Net Flow: 24h={fmt_stable_flow(sol_sf_24h)} / 7d={fmt_stable_flow(sol_sf_7d)}\n"
        ctx += f"- Technicals: {fmt_tech(sol_market)}\n"
        sol_liq_ratio = sol_liq_long / sol_liq_short if sol_liq_short > 0 else 0
        sol_liq_signal = "⚠️ LONG_FLUSH" if sol_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if sol_liq_short > sol_liq_long * 2 else "BALANCED")
        ctx += f"- [爆仓L/S比 ⚠️DIFFERENT FROM 持仓比] Liquidated Longs ${sol_liq_long:,.0f} / Liquidated Shorts ${sol_liq_short:,.0f} | Liq-Ratio(Long/Short)={sol_liq_ratio:.2f} [{sol_liq_signal}]\n"
        
        ctx += "\n=== BITCOIN (BTC) CONTRACT DATA ===\n"
        btc_ls = btc_market.get("whale_ls_ratio", 0)
        btc_pos = btc_market.get("whale_pos_ratio", 0)
        btc_sent = btc_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX Whale Account Ratio={btc_ls:.2f} (>1 more longs, <1 more shorts) / Position Size Ratio={btc_pos:.2f}\n"
        ctx += f"- OKX Top Trader Sentiment: {btc_sent:.2f} (Whale Bias: {'Bullish' if btc_sent > 0.5 else 'Bearish' if btc_sent < 0.5 else 'Neutral'})\n"
        ctx += f"- Technicals: {fmt_tech(btc_market)}\n"
        btc_liq_ratio = btc_liq_long / btc_liq_short if btc_liq_short > 0 else 0
        btc_liq_signal = "⚠️ LONG_FLUSH" if btc_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if btc_liq_short > btc_liq_long * 2 else "BALANCED")
        ctx += f"- [爆仓L/S比 ⚠️DIFFERENT FROM 持仓比] Liquidated Longs ${btc_liq_long:,.0f} / Liquidated Shorts ${btc_liq_short:,.0f} | Liq-Ratio(Long/Short)={btc_liq_ratio:.2f} [{btc_liq_signal}]\n"
        
        ctx += "\n=== BNB CHAIN (BNB) CONTRACT DATA ===\n"
        bnb_ls = bnb_market.get("whale_ls_ratio", 0)
        bnb_pos = bnb_market.get("whale_pos_ratio", 0)
        bnb_sent = bnb_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX Whale Account Ratio={bnb_ls:.2f} (>1 more longs, <1 more shorts) / Position Size Ratio={bnb_pos:.2f}\n"
        ctx += f"- OKX Top Trader Sentiment: {bnb_sent:.2f} (Whale Bias: {'Bullish' if bnb_sent > 0.5 else 'Bearish' if bnb_sent < 0.5 else 'Neutral'})\n"
        ctx += f"- Technicals: {fmt_tech(bnb_market)}\n"
        bnb_liq_ratio = bnb_liq_long / bnb_liq_short if bnb_liq_short > 0 else 0
        bnb_liq_signal = "⚠️ LONG_FLUSH" if bnb_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if bnb_liq_short > bnb_liq_long * 2 else "BALANCED")
        ctx += f"- [爆仓L/S比 ⚠️DIFFERENT FROM 持仓比] Liquidated Longs ${bnb_liq_long:,.0f} / Liquidated Shorts ${bnb_liq_short:,.0f} | Liq-Ratio(Long/Short)={bnb_liq_ratio:.2f} [{bnb_liq_signal}]\n"
        
        ctx += "\n=== DOGECOIN (DOGE) CONTRACT DATA ===\n"
        doge_ls = doge_market.get("whale_ls_ratio", 0)
        doge_pos = doge_market.get("whale_pos_ratio", 0)
        doge_sent = doge_market.get("top_trader_sentiment", 0.5)
        ctx += f"- OKX Whale L/S Ratio: Account={doge_ls:.2f} / Position={doge_pos:.2f}\n"
        ctx += f"- OKX Top Trader Sentiment: {doge_sent:.2f} (Whale Bias: {'Bullish' if doge_sent > 0.5 else 'Bearish' if doge_sent < 0.5 else 'Neutral'})\n"
        ctx += f"- Technicals: {fmt_tech(doge_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs ${doge_liq_long:,.0f} / Shorts ${doge_liq_short:,.0f}\n"
        
        ctx += "\n*INSTRUCTION*: If 24h Sentiment is higher than 7d, it indicates SHARP ACCUMULATION. If 24h is significantly lower, it indicates a POTENTIAL CLIFF DUMP. Prioritize sustained 7d trends for safety.*\n"
        
        # Add Macro Context (New Layer)
        macro = data.get("macro", {})
        fed = macro.get("fed_futures", {})
        japan = macro.get("japan_macro", {})
        liq = macro.get("liquidity_monitor", {})
        
        ctx += "\n=== GLOBAL MACRO CONTEXT (CRITICAL) ===\n"
        ctx += f"- Fed Futures Rate: {fed.get('implied_rate', 0)}% (Trend: {fed.get('trend', 'Neutral')})\n"
        if 'change_5d_bps' in fed:
             ctx += f"  * 5d Change: {fed['change_5d_bps']} bps\n"
        
        ctx += f"- USD/JPY: {japan.get('price', 0)} (Trend: {japan.get('trend', 'Neutral')})\n"
        if 'change_5d_pct' in japan:
             ctx += f"  * 5d Change: {japan['change_5d_pct']}%\n"
             
        ctx += f"- VIX: {liq.get('vix', {}).get('price', 0)} (Trend: {liq.get('vix', {}).get('trend', 'Neutral')})\n"
        ctx += f"- DXY: {liq.get('dxy', {}).get('price', 0)} (Trend: {liq.get('dxy', {}).get('trend', 'Neutral')})\n"
        
        # Add AI Narrative from Crypto Brain
        ai_narrative = data.get("ai_summary", {}).get("en", "")
        if ai_narrative:
            ctx += f"\n=== UPSTREAM AI ANALYSIS ===\n{ai_narrative[:500]}...\n"
            
        return ctx, data
        
    except Exception as e:
        return f"Error reading whale data: {e}", {}

def get_news_context():
    """
    Fetch news and on-chain context from the global snapshot.
    """
    snapshot_path = DATA_DIR / "global_onchain_news_snapshot.json"
    if not snapshot_path.exists():
        return "No news data available."
        
    try:
        with open(snapshot_path, "r") as f:
            data = json.load(f)
            
        # 1. News - Collect from all available sources
        news_root = data.get("news", {})
        news_items = news_root.get("items", {})
        all_news = []
        
        # Calendar (Economic Data) - High Priority
        calendar_news = news_items.get("calendar", {}).get("items", [])
        calendar_str = ""
        if calendar_news:
            calendar_str = "Economic Calendar (This Week):\n"
            for item in calendar_news[:5]:
                calendar_str += f"- {item.get('title')} [{item.get('published')}]\n"
        
        # General News
        for source_key in ["macro", "bitcoin", "ethereum", "general"]:
            source_news = news_items.get(source_key, {}).get("items", [])
            all_news.extend(source_news[:3])  # Take top 3 from each source
        
        news_str = "Latest News (CRITICAL: For EACH item, you MUST assess: [PRICE_IN] already reflected in price, [FERMENTING] still unfolding/not priced, or [FADING] impact fading):\n"
        if all_news:
            for item in all_news[:10]:  # Show max 10 total general news
                sentiment = item.get('sentiment', 'Neutral')
                published = item.get('published', 'N/A')
                summary = item.get('summary_cn') or item.get('summary', '')
                # Truncate summary to keep the prompt lean
                summary_short = summary[:120].replace('\n', ' ') if summary else ''
                news_str += f"- [{sentiment}] {item.get('title')} ({published})\n"
                if summary_short:
                    news_str += f"  → {summary_short}...\n"
        else:
            news_str += "No recent news available.\n"

        news_str += "\n[NEWS ANALYSIS INSTRUCTION] For each news item above, judge:\n"
        news_str += "  * PRICE_IN: If it's old news (>12h) OR price already moved significantly in response → label PRICE_IN, no further impact expected.\n"
        news_str += "  * FERMENTING: If news is <6h old AND price hasn't fully reacted yet → label FERMENTING, may still drive further movement.\n"
        news_str += "  * FADING: If news was bullish/bearish but price reversed → narrative is dying, contrarian opportunity.\n"
        news_str += "  Incorporate this assessment into your [Narrative Validation] section.\n"
            
        # Combine Calendar + News
        final_news_context = f"{calendar_str}\n{news_str}" if calendar_str else news_str
            
        # 3. Fear & Greed
        fng = data.get("fear_greed", {}).get("latest") or data.get("fear_greed", {})
        fng_str = f"\nFear & Greed Index: {fng.get('value')} ({fng.get('classification')})\n"
        
        return final_news_context + fng_str
        
    except Exception as e:
        return f"Error reading news data: {e}"

def get_daily_context_summary():
    """
    Fetch 1D candles directly from OKX to calculate SMA200 and determine Market Regime.
    """
    import requests
    summary = "=== 1D MACRO TREND & REGIME ===\n"
    coins = ["BTC", "ETH", "SOL", "BNB", "DOGE"]
    
    for symbol in coins:
        try:
            instId = f"{symbol}-USDT-SWAP"
            # Fetch 300 candles for SMA200
            url = f"https://www.okx.com/api/v5/market/candles?instId={instId}&bar=1D&limit=300"
            res = requests.get(url, timeout=(5, 10)).json()
            
            if res["code"] != "0" or not res["data"]:
                continue
                
            # Data is Newest -> Oldest
            # We need Oldest -> Newest for pandas rolling, but we can do it manually or simply list logic
            candles = res["data"]
            closes = [float(c[4]) for c in candles] # index 4 is close
            closes.reverse() # Now Oldest -> Newest
            
            current_price = closes[-1]
            
            # Metric 1: SMA 50
            if len(closes) >= 50:
                sma50 = sum(closes[-50:]) / 50
            else:
                sma50 = current_price
                
            # Metric 2: SMA 200 (The King of Trend)
            if len(closes) >= 200:
                sma200 = sum(closes[-200:]) / 200
            else:
                sma200 = 0 # Not enough data
            
            # Determine Regime
            regime = "NEUTRAL"
            if sma200 > 0:
                if current_price > sma200:
                    regime = "BULL"
                else:
                    regime = "BEAR"
            
            summary += f"- **{symbol}**: REGIME={regime} (Price ${current_price:.2f} vs SMA200 ${sma200:.2f})\n"
            summary += f"  - Trend: {'BULLISH' if current_price > sma50 else 'BEARISH'} (vs SMA50 ${sma50:.2f})\n"
            
            if symbol == "BTC":
                # Inject Global Regime Marker
                summary += f"  - **GLOBAL MARKET STATE**: {regime} MARKET\n"

        except Exception as e:
            print(f"Error fetching 1D context for {symbol}: {e}")
            
    return summary

def validate_and_enforce_decision(decision, whale_data_obj, daily_context, fear_index, executor):
    """
    Risk Management Layer (The "Supervisor").
    Sanitizes and overrides AI decisions based on hard rules.
    """
    if not decision:
        return decision

    validated_actions = []
    
    # --- 1. GATHER INTEL ---
    # A. Position Count
    current_positions = executor.get_open_position_count()
    MAX_POSITIONS = 3
    
    # B. Financials (Equity & Exposure)
    equity = executor.get_account_equity()
    exposure = executor.get_total_exposure()
    current_long_exposure = exposure['long']
    current_short_exposure = exposure['short']
    
    # C. Market Regime (Parse from Context string)
    # Default to NEUTRAL if not found
    regime = "NEUTRAL"
    if "GLOBAL MARKET STATE: BULL" in daily_context:
        regime = "BULL"
    elif "GLOBAL MARKET STATE: BEAR" in daily_context:
        regime = "BEAR"
        
    print(f"🛡️ RISK: State={regime} | Pos={current_positions} | Equity=${equity:.0f} | LongExp=${current_long_exposure:.0f} | ShortExp=${current_short_exposure:.0f}")

    # --- 2. DEFINE LIMITS ---
    # Exposure Caps (% of Equity) - Reduced by 2% for Fees/Buffer
    if regime == "BULL":
        MAX_LONG_CAP = 0.98   # 98%
        MAX_SHORT_CAP = 0.30  # 30%
    elif regime == "BEAR":
        MAX_LONG_CAP = 0.40   # 40%
        MAX_SHORT_CAP = 0.78  # 78%
    else: # NEUTRAL
        MAX_LONG_CAP = 0.48
        MAX_SHORT_CAP = 0.48
        
    # Leverage Cap (Volatility Guard)
    is_extreme_market = (fear_index < 20) or (fear_index > 80)
    MAX_LEVERAGE = 2 if is_extreme_market else 5 # Lowered base limit to 5x as agreed
    
    # Merge newly structured actions back into a flat list for legacy processing
    raw_actions = []
    
    # --- 1.2 PORTFOLIO INTEGRITY CHECK (FILL MISSING) ---
    # Ensure every open position has a corresponding entry in portfolio_management
    try:
        open_positions = executor.get_all_positions()
        pm = decision.get("portfolio_management", {})
        if not isinstance(pm, dict):
            pm = {}
            decision["portfolio_management"] = pm
            
        for pos in open_positions:
            sym = pos["symbol"]
            # Case-insensitive match check
            found = False
            for pm_sym in pm.keys():
                if pm_sym.upper() == sym.upper():
                    found = True
                    break
            
            if not found:
                print(f"🛡️ INTEGRITY: AI missed {sym} in portfolio_management. Auto-filling 'hold'.")
                pm[sym] = {
                    "action": "hold",
                    "action_logic": {
                        "zh": "系统补丁：AI未返回该持仓指令，默认维持当前状态以规避逻辑空缺风险。",
                        "en": "System Patch: AI missed this symbol in response. Auto-filling 'hold' to ensure constant monitoring."
                    }
                }
    except Exception as e:
        print(f"⚠️ Portfolio Integrity Check Failed: {e}")

    # A. Existing Portfolio
    pm = decision.get("portfolio_management", {})
    for symbol, data in pm.items():
        data["symbol"] = symbol
        raw_actions.append(data)
        
    # B. New Opportunities
    raw_actions.extend(decision.get("new_opportunities", []))

    for action in raw_actions:
        symbol = action.get("symbol")
        act_type = action.get("action")
        # Ensure reasons are mapped correctly for frontend (Normalize action_logic -> entry_reason)
        if not action.get("entry_reason"):
             action["entry_reason"] = action.get("action_logic", {})
        
        try:
            size_usd = float(str(action.get("position_size_usd", 0)).replace('$', '').replace(',', ''))
        except ValueError:
            size_usd = 0.0
        
        if act_type == "hold":
            # RECOGNITION: We keep 'hold' in validated_actions so users can see the logic in UI
            validated_actions.append(action)
            continue

        MIN_ORDER_USD = 50.0
        # Skip if size is zero or too tiny (prevents dust orders)
        if size_usd < MIN_ORDER_USD and act_type.startswith("open_"):
             reason = f"🛡️ Trade size ${size_usd:.2f} too small (< ${MIN_ORDER_USD}). REJECTED."
             print(f"{reason} Skipping {symbol}.")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue
            
        # TRACKING: Close actions reduce exposure
        if "close" in act_type:
            current_positions = max(0, current_positions - 1)
            # We don't know exact size to reduce without tracking, so we just allow it.
            # Closing reduces risk, so it's always allowed.
            validated_actions.append(action)
            continue
            
        # TRACKING: Adjust SL
        if act_type == "adjust_sl":
            validated_actions.append(action)
            continue
            
        # --- NEW Layer: Whale Dump Guard (Token vs Stable Flow) ---
        # Prevents "Inflow to Sell" traps
        sym_upper = symbol.upper()
        # Extract flows from context/data if available
        # (Assuming the logic to parse these exists or we pull from whale_data_obj)
        s_data = whale_data_obj.get(symbol.lower(), {}).get('stats_24h', {})
        t_flow = s_data.get('token_net_flow', 0)
        st_flow = s_data.get('stablecoin_net_flow', 0)
        
        if act_type == "open_long" and t_flow > 0 and st_flow < 0:
             reason = f"🛡️ WHALE TRAP: {symbol} has Token INFLOW (${t_flow:.0f}) but Stablecoin OUTFLOW (${st_flow:.0f}). This is an 'Exchange Dump' setup, not accumulation. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue

        # --- NEW Layer: Liquidity Trap Guard (L/S Ratio) ---
        # Prevents chasing squeezes that are already over
        liq_long = s_data.get('liquidation_long_usd', 0)
        liq_short = s_data.get('liquidation_short_usd', 1) # avoid div by zero
        ls_ratio = liq_long / max(liq_short, 1.0)
        
        if act_type == "open_long" and ls_ratio < 0.1:
             reason = f"🛡️ LIQUIDITY TRAP: {symbol} L/S Ratio is too low ({ls_ratio:.2f}). Shorts already squeezed. No more fuel to go higher. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue
             
        if act_type == "open_short" and ls_ratio > 10.0:
             reason = f"🛡️ REVERSAL TRAP: {symbol} L/S Ratio is too high ({ls_ratio:.2f}). Longs already flushed. Expect mean-reversion bounce. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue

        # --- NEW Layer: Volatility & Risk Refinement (NATR & 2% NAV) ---


        # Refines size and stop_loss BEFORE exposure checks
        sym_key = symbol.lower()
        m_data = whale_data_obj.get(sym_key, {}).get('market', {})
        natr = m_data.get('natr_percent', 3.0) # Default to 3% if data missing
        entry_price = m_data.get('price', 0)
        
        if entry_price > 0 and act_type.startswith("open_"):
            min_stop_dist_pct = 1.5 * natr
            exit_plan = action.get("exit_plan", {})
            sl_input = exit_plan.get("stop_loss")
            
            # 1. Price Parsing
            try:
                sl_price = float(str(sl_input).replace('$', '').replace(',', '')) if sl_input and str(sl_input) != "None" and not isinstance(sl_input, str) else 0
                if isinstance(sl_input, str) and not sl_input.replace('.', '', 1).isdigit():
                    sl_price = 0 # Handle "Dynamic..." strings
            except ValueError:
                sl_price = 0
            
            if sl_price > 0:
                current_sl_dist_pct = abs(entry_price - sl_price) / entry_price * 100
            else:
                current_sl_dist_pct = 0
                
            # 2. Enforce Minimum Stop Distance (1.5x NATR)
            enforced_sl_pct = max(current_sl_dist_pct, min_stop_dist_pct)
            
            if enforced_sl_pct > current_sl_dist_pct:
                # Recalculate price
                if "long" in act_type:
                    new_sl_price = entry_price * (1 - enforced_sl_pct / 100)
                else:
                    new_sl_price = entry_price * (1 + enforced_sl_pct / 100)
                
                action["exit_plan"]["stop_loss"] = round(new_sl_price, 4)
                if current_sl_dist_pct > 0:
                    print(f"🛡️ RISK: Widening Stop to 1.5x NATR ({enforced_sl_pct:.2f}%) for {symbol}")
                else:
                    print(f"🛡️ RISK: Enforcing NATR Stop ({enforced_sl_pct:.2f}%) for {symbol}")
            
            # 3. NAV Risk Cap (2% Max Risk)
            # If (Size * StopDist%) > (Equity * 2%), we MUST reduce Size.
            max_risk_usd = equity * 0.02
            current_risk_usd = (enforced_sl_pct / 100) * size_usd
            
            if current_risk_usd > max_risk_usd:
                refined_size_usd = max_risk_usd / (enforced_sl_pct / 100)
                print(f"🛡️ RISK: Downsizing {symbol} from ${size_usd:.0f} to ${refined_size_usd:.0f} to meet 2% NAV loss limit")
                action["position_size_usd"] = round(refined_size_usd, 2)
                size_usd = refined_size_usd # Update for subsequent checks

        # CHECK: Open Actions
        if act_type.startswith("open_"):
            # A. Position Count Limit
            if current_positions >= MAX_POSITIONS:
                reason = f"🛡️ Max positions ({MAX_POSITIONS}) reached."
                print(f"{reason} Skipping {symbol}.")
                action["action"] = "REJECTED"
                action["reason"] = reason
                validated_actions.append(action)
                continue
            
            # B. Exposure Cap Limit
            if "long" in act_type:
                projected_long = current_long_exposure + size_usd
                limit_usd = equity * MAX_LONG_CAP
                TOLERANCE = 5.0 # Allow $5 overage for market/decimal noise
                if projected_long > (limit_usd + TOLERANCE):
                    reason = f"🛡️ Long Cap Exceeded. Projected ${projected_long:.0f} > Limit ${limit_usd:.0f} ({MAX_LONG_CAP*100}%)."
                    print(f"{reason} Skipping {symbol}.")
                    action["action"] = "REJECTED"
                    action["reason"] = reason
                    validated_actions.append(action)
                    continue
                # Approved -> Update sim tracker
                current_long_exposure += size_usd
                
            elif "short" in act_type:
                projected_short = current_short_exposure + size_usd
                limit_usd = equity * MAX_SHORT_CAP
                TOLERANCE = 5.0
                if projected_short > (limit_usd + TOLERANCE):
                    reason = f"🛡️ Short Cap Exceeded. Projected ${projected_short:.0f} > Limit ${limit_usd:.0f} ({MAX_SHORT_CAP*100}%)."
                    print(f"{reason} Skipping {symbol}.")
                    action["action"] = "REJECTED"
                    action["reason"] = reason
                    validated_actions.append(action)
                    continue
                # Approved -> Update sim tracker
                current_short_exposure += size_usd

            # C. Leverage Cap
            raw_lev = action.get("leverage", 1)
            if raw_lev > MAX_LEVERAGE:
                print(f"🛡️ RISK: Capping leverage for {symbol} from {raw_lev}x to {MAX_LEVERAGE}x")
                action["leverage"] = MAX_LEVERAGE
            
            validated_actions.append(action)
            current_positions += 1

    
    decision["actions"] = validated_actions
    return decision

def run_agent():
    print("🤖 Activating Agent Dolores (Whale Edition)...")
    
    # Initialize Executor (Shadow Mode by default)
    # TODO: Set shadow_mode=False via env var for REAL TRADING later
    executor = OKXExecutor()
    
    # 1. Load Qlib Payload (Live Check)
    qlib_payload_obj = {}
    qlib_stale_warning = ""
    if PAYLOAD_PATH.exists():
        try:
            with open(PAYLOAD_PATH, "r") as f:
                qlib_payload_obj = json.load(f)
            
            # Check for staleness (e.g., more than 24h old)
            as_of_str = qlib_payload_obj.get("as_of", "2000-01-01")
            as_of_dt = datetime.strptime(as_of_str, "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - as_of_dt).total_seconds() > 86400:
                qlib_stale_warning = f"⚠️ WARNING: Qlib scores are STALE (As of {as_of_str}). Use with caution."
        except Exception as e:
            qlib_payload_obj = {"error": str(e)}

    qlib_payload_str = json.dumps(qlib_payload_obj, indent=2)

    # 2. Prepare Prompt
    portfolio_state = get_portfolio_state(executor)
    news_context = get_news_context()
    
    # NEW: Get Whale Data
    whale_context, whale_data_obj = get_whale_data()
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    final_prompt = SYSTEM_PROMPT.replace("{{CURRENT_TIMESTAMP}}", current_time)
    
    # Precise Qlib Injection with Warning
    qlib_block = f"[[ QLIB ANALYSIS PAYLOAD ]]\n{qlib_payload_str}\n{qlib_stale_warning}"
    final_prompt = final_prompt.replace("{{QLIB_JSON_PAYLOAD}}", qlib_block)
    
    final_prompt = final_prompt.replace("{{WHALE_CONTEXT}}", whale_context)
    
    # Add Daily Context + MEMORY INJECTION (DISABLED)
    memory_context = "" # memory.get_recent_performance()
    daily_context = get_daily_context_summary()
    
    # Combined Context
    combined_context = f"{daily_context}\n\n{memory_context}"
    final_prompt = final_prompt.replace("{{DAILY_CONTEXT}}", combined_context)
    
    final_prompt = final_prompt.replace("{{PORTFOLIO_STATE_JSON}}", portfolio_state)
    
    # DYNAMIC MAPPING FORCE
    p_state_obj = json.loads(portfolio_state)
    active_symbols = [p["symbol"] for p in p_state_obj.get("positions", [])]
    if not active_symbols:
        final_prompt = final_prompt.replace("{{MANDATORY_SYMBOLS_LIST}}", "NONE (Portfolio is empty)")
    else:
        final_prompt = final_prompt.replace("{{MANDATORY_SYMBOLS_LIST}}", ", ".join(active_symbols))
    
    final_prompt = final_prompt.replace("{{NEWS_CONTEXT}}", news_context)

    # 2.5 Inject Dynamic Risk Limits
    # Determine Regime
    regime = "NEUTRAL"
    if "GLOBAL MARKET STATE: BULL" in daily_context: regime = "BULL"
    elif "GLOBAL MARKET STATE: BEAR" in daily_context: regime = "BEAR"

    # Define Caps (Sync with validate_and_enforce_decision)
    if regime == "BULL":
        max_long_cap = 0.98
        max_short_cap = 0.30
    elif regime == "BEAR":
        max_long_cap = 0.40
        max_short_cap = 0.78
    else: # NEUTRAL
        max_long_cap = 0.48
        max_short_cap = 0.48

    # Calculate Values
    equity = executor.get_account_equity()
    exposure = executor.get_total_exposure()
    curr_long = exposure['long']
    curr_short = exposure['short']

    max_long_usd = equity * max_long_cap
    max_short_usd = equity * max_short_cap

    MIN_TRADE_USD = 100.0  # Require at least $100 room to suggest a trade to AI
    
    # Calculate available room with a buffer
    raw_avail_long = max_long_usd - curr_long - 10
    avail_long = max(0, raw_avail_long) if raw_avail_long >= MIN_TRADE_USD else 0
    
    raw_avail_short = max_short_usd - curr_short - 10
    avail_short = max(0, raw_avail_short) if raw_avail_short >= MIN_TRADE_USD else 0

    # Extract Fear & Greed Index (needed for validate_and_enforce_decision)
    try:
        fear_index = float(whale_data_obj.get("fear_greed", {}).get("latest", {}).get("value", 50))
    except Exception:
        fear_index = 50  # Default: neutral, no extreme leverage restrictions

    # Replace Placeholders
    final_prompt = final_prompt.replace("{{MARKET_REGIME}}", regime)
    final_prompt = final_prompt.replace("{{MAX_LONG_LIMIT_USD}}", f"{max_long_usd:.0f}")
    final_prompt = final_prompt.replace("{{MAX_LONG_PCT}}", f"{max_long_cap*100:.0f}")
    final_prompt = final_prompt.replace("{{MAX_SHORT_LIMIT_USD}}", f"{max_short_usd:.0f}")
    final_prompt = final_prompt.replace("{{MAX_SHORT_PCT}}", f"{max_short_cap*100:.0f}")
    final_prompt = final_prompt.replace("{{CURR_LONG_EXP_USD}}", f"{curr_long:.0f}")
    final_prompt = final_prompt.replace("{{CURR_SHORT_EXP_USD}}", f"{curr_short:.0f}")
    final_prompt = final_prompt.replace("{{AVAILABLE_LONG_USD}}", f"{avail_long:.0f}")
    final_prompt = final_prompt.replace("{{AVAILABLE_SHORT_USD}}", f"{avail_short:.0f}")
    
    # 3. Call DeepSeek API with OpenAI SDK (with manual retry loop)
    try:
        MAX_RETRIES = 5
        RETRY_DELAY = 5 # base seconds
        
        decision = None
        content = None
        
        for attempt in range(MAX_RETRIES):
            try:
                print(f"🤔 Dolores is thinking... (Attempt {attempt+1}/{MAX_RETRIES}, Timeout: 120s)")
                
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": final_prompt},
                        {"role": "user", "content": "Analyze the market reality (Whales vs Retail). Detect traps. Generate trading actions."}
                    ],
                    response_format={"type": "json_object"},
                    timeout=120
                )
                
                content = response.choices[0].message.content
                # Parse JSON
                decision = json.loads(content)
                break # Success!
                
            except Exception as e:
                wait_time = RETRY_DELAY * (2 ** attempt) # Exponential backoff
                print(f"⚠️ Attempt {attempt+1} failed: {e}")
                if attempt == MAX_RETRIES - 1 or "401" in str(e):
                    print("🔄 DeepSeek failing... Falling back to Gemini Pro...")
                    try:
                        # Fallback to Gemini 2.5
                        model = genai.GenerativeModel('gemini-2.5-pro')
                        prompt_with_instructions = final_prompt + "\n\nUser request: Analyze the market reality (Whales vs Retail). Detect traps. Generate trading actions.\nIMPORTANT: Output MUST be a valid JSON object matching the requested schema. DO NOT wrap the output in markdown code blocks."
                        
                        gemini_res = model.generate_content(
                            prompt_with_instructions,
                            generation_config={"response_mime_type": "application/json"}
                        )
                        content = gemini_res.text
                        decision = json.loads(content)
                        break
                    except Exception as gemini_err:
                        print(f"❌ Gemini fallback also failed: {gemini_err}")
                        if attempt == MAX_RETRIES - 1:
                            raise gemini_err
                
                if attempt < MAX_RETRIES - 1:
                    print(f"🔄 Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        
        # Validate & Enforce
        decision = validate_and_enforce_decision(decision, whale_data_obj, daily_context, fear_index, executor)
            
        print("\n💡 Dolores' Decision:")
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        
        # === NEW: EXECUTION LAYER ===
        # Re-fetch actions from decision (which now includes validated list)
        actions = decision.get("actions", [])
        
        for act in actions:
            symbol = act.get("symbol")
            action_type = act.get("action")
            
            # Logic Mapping for reason (English)
            reason_obj = act.get("action_logic") or act.get("entry_reason") or {}
            reason_txt = reason_obj.get("en", "Maintaining position based on trend.")

            try:
                amount = float(str(act.get("position_size_usd", 0)).replace('$', '').replace(',', ''))
            except ValueError:
                amount = 0.0
                
            leverage = act.get("leverage", 1)
            
            exit_plan = act.get("exit_plan", {})
            sl = exit_plan.get("stop_loss")
            tp = exit_plan.get("take_profit")
            
            # Filter for actual executable trade actions
            is_trade = any(keyword in action_type for keyword in ["open_", "close", "adjust_sl", "reduce_"])
            
            if is_trade and action_type != "REJECTED" and action_type != "hold":
                print(f"\n🚀 Triggering Executor for {symbol} ({action_type})...")
                
                # Fetch NATR for the Risk Shield in Executor
                coin_natr = whale_data_obj.get(symbol.lower(), {}).get('market', {}).get('natr_percent')
                
                executor.execute_trade(symbol, action_type, amount, leverage, stop_loss=sl, take_profit=tp, natr_percent=coin_natr)

                
                # LOG TO MEMORY
                try:
                    sym_lower = symbol.lower()
                    market_snapshot = whale_data_obj.get(sym_lower, {}).get('market', {})
                    entry_reason = act.get('entry_reason', {})
                    # Add reason string for text logs
                    reason_txt = entry_reason.get('en', 'Driven by whale accumulation.')
                    
                    # memory.log_trade(symbol, action_type, amount, entry_reason, market_snapshot)
                    
                    # 🔔 SEND NOTIFICATION (Telegram/Discord)
                    notify_trade_execution(
                        symbol=symbol,
                        action=action_type,
                        size=f"ALL" if "close" in action_type and amount == 0 else f"${amount} ({leverage}x)",
                        entry_price="MARKET", # Execution is market/limit based on executor
                        sl=sl,
                        tp=tp,
                        reason=reason_txt
                    )
                    
                except Exception as log_err:
                    print(f"⚠️ Memory/Notify Log Error: {log_err}")
        
        # Save decision log
        try:
            from db_client import db
            history = db.get_data("agent_decision_log", [])
            if not isinstance(history, list):
                history = [history] if history else []
        except Exception as e:
            print(f"⚠️ Failed to load history from DB: {e}")
            history = []
        
        # Add timestamp (Force overwrite with local time UTC+8)
        import datetime as dt
        utc_now = dt.datetime.utcnow()
        beijing_time = utc_now + dt.timedelta(hours=8)
        decision["timestamp"] = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
            
        history.insert(0, decision)
        history = history[:50]
        
        print(f"💾 Saving decision log to DB")
        try:
            from db_client import db
            db.save_data("agent_decision_log", history)
            print("✅ Decision Log Saved Successfully!")
        except Exception as e:
            print(f"❌ FAILED to save log to DB: {e}")
                
    except Exception as e:
        print(f"❌ Error calling DeepSeek (OpenAI SDK): {e}")

if __name__ == "__main__":
    run_agent()
