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
from openai import OpenAI
import time
from okx_executor import OKXExecutor
from notifier import notify_trade_execution # Restored Notification System

# Load environment variables
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"

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
                    "rsi": market_snapshot.get('rsi_14', 50),
                    "adx": market_snapshot.get('adx_14', 0),
                    "whale_flow": market_snapshot.get('whale_flow', 0),
                    "bb_width": market_snapshot.get('bb_width'),
                    "bb_trend": market_snapshot.get('bb_trend')
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
        Returns a summary of recent trades to inject into AI prompt.
        """
        if not AGENT_MEMORY_PATH.exists():
            return "No trading history yet."
            
        try:
            with open(AGENT_MEMORY_PATH, "r") as f:
                history = json.load(f)
            if not history: return "No trading history yet."
            
            # Simple summarization of last 5 trades
            recent = history[-5:]
            summary = "=== 📜 RECENT TRADE MEMORY (LEARN FROM THIS) ===\n"
            for t in recent:
                summary += f"- {t['timestamp'][:16]} {t['action']} {t['symbol']} @ {t['entry_price']}\n"
                summary += f"  Rationale: {t['reason'].get('en', '')[:100]}...\n"
                
                if t.get('outcome') == "Closed" or "close" in t['action'].lower():
                    summary += f"  STATUS: Completed (Position Exited)\n"
                elif t.get('outcome'):
                    summary += f"  RESULT: {t['outcome']}\n"
                else:
                    summary += f"  STATUS: Open\n"
            return summary
        except Exception as e:
            return f"Error reading history: {e}"

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

🟪 2.2 WHALE & LIQUIDATION REALITY (THE TRUTH LAYER)
This data comes from direct on-chain monitoring and exchange liquidation feeds.
**IT OVERRIDES PURE TECHNICALS.**

{{WHALE_CONTEXT}}

**INTERPRETATION RULES:**
1. **Accumulation Signal**: If Prices are dropping, but Token Net Flow is POSITIVE (Whales buying) + High Long Liquidations (Retail capitulating) -> **BULLISH DIVERGENCE (Buy the dip)**.
2. **Distribution Signal**: If Prices are rising, but Token Net Flow is NEGATIVE (Whales selling) + High Short Liquidations -> **BEARISH DIVERGENCE (Sell the rip)**.
3. **Squeeze Warning**: Negative Funding + High "Retail Pain" (Oversold RSI) -> **SHORT SQUEEZE IMMINENT**.

🟦 2.1 MACRO TREND (1D TIMEFRAME)
Use this daily context to filter 4H signals.
- **Trend**: Price vs SMA50 (Bullish if Price > SMA50).
- **Structure**: Recent Highs/Lows.

{{DAILY_CONTEXT}}

🟪 2.3 MARKET REGIME (THE LAW)
Pay close attention to **GLOBAL MARKET STATE** in the Daily Context above.
1. **BEAR MARKET (Price < SMA200)**:
   - **Primary Bias**: SHORT.
   - **Longs**: Only allowed if "Whale Accumulation" is Extreme AND "Liquidation Signal" is present. Max Leverage 2x.
   - **Shorts**: Aggressive shorts allowed on pumps (Distribution).
2. **BULL MARKET (Price > SMA200)**:
   - **Primary Bias**: LONG.
   - **Shorts**: Only allowed if "Whale Distribution" is Extreme. Max Leverage 2x.
   - **Longs**: Aggressive longs allowed on dips (Accumulation).

🟨 3. NEWS & ON-CHAIN CONTEXT (OPTIONAL)
{{NEWS_CONTEXT}}

🟥 4. ANALYSIS LOGIC (The "Dolores" Method)

A. NARRATIVE VS REALITY CHECK (Crucial Step)
For each major news item or market move, ask:
- **Impulse**: Is this a NEW driver that changes the thesis? (Price moves WITH news).
- **Priced In**: Is this old news? (Price fades or ignores good news).
- **Divergence**: Good News + Bad Price = Distribution (Bearish). Bad News + Good Price = Accumulation (Whale Trap - Bullish).
- Compare "Retail News" vs "Whale Reality" (On-chain flow). If they disagree, follow the Whales.

B. THE PAIN TRADE (Liquidity Hunting)
Identify where the crowd is trapped:
- **Long Squeeze Risk**: Funding > 0.03% (Crowded Longs) + Price Stalling + High Long Liquidations. -> DANGER for Longs.
- **Short Squeeze Opportunity**: Funding < -0.01% (Crowded Shorts) + Price Holding Support + Whale Buying. -> OPPORTUNITY for Longs.
- **Liquidity Trap**: Late chasers entering at resistance (High Funding + High RSI).

C. HYPOTHESIS MENU (Generate 3 Scenarios)
For top candidates, evaluate:
1.  **Trend Following**: Models Align + Whale Accumulation + Normal Funding. (Go with the flow).
2.  **Mean Reversion**: Extreme RSI (>70 or <30) + Liquidation Spike + Extreme Funding. (Fade the move).
3.  **Whale Front-Run**: Massive Token Inflow detected while retail is panicking. (Bet on the Smart Money).

� 4D. TACTICAL DISCIPLINE (THE BATTLEFIELD RULES - MUST OBEY)

1. **Anti-Liquidity Rush (Do not fight the cascade)**:
   - If Liquidations are **SIGNIFICANTLY LOPSIDED** (e.g., one side is 3x+ the other) OR price is moving vertically on high volume, DO NOT open a reverse trade immediately. 
   - Treat these liquidations as **FUEL** for the current move. Acknowledge that the move is likely to overshoot. Wait for the liquidation spike to plateau or a 4H candle to close with a long wick before considering a reversal.
2. **Funding Trap Check**:
   - Before going LONG: Funding Rate should ideally be flat or negative (Retail is fearful/shorting). If Funding is high (>0.03%), the long is crowded and dangerous.
   - Before going SHORT: Funding Rate should ideally be flat or positive (Retail is greedy/longing). If Funding is very negative (<-0.01%), the short is crowded and prone to a squeeze.
3. **Left Signal, Right Entry (Wait for Confirmation)**:
   - Whale Divergence is a "Left-side" warning signal. Do not jump in just because whales are buying.
   - Wait for a "Right-side" confirmation: e.g., price breaking a recent 4H high (for longs) or low (for shorts), or RSI starting to turn back from extreme levels.

�🟧 5. PORTFOLIO & RISK MANAGEMENT
Current State:
{{PORTFOLIO_STATE_JSON}}

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
    "zh": "必须是中文，综合叙述（3-4句话）。1. 首先进行【叙事校验】（Section 4A），判断当前驱动力是Impulse还是已定价。2. 结合【痛苦交易】（4B）和【战场纪律】（4D），指出市场是否处于“爆仓踩踏”中，是否有足够的“燃料”支撑继续上涨/下跌。3. 阐明选择的【假设分析】剧本（4C）。",
    "en": "English translation of the above Chinese summary."
  },
  "context_analysis": {
    "technical_signal": { "zh": "技术面概括 (RSI, ADX...)", "en": "Brief technical summary." },
    "macro_onchain": { "zh": "鲸鱼数据与资金费率分析", "en": "Whale flow & funding analysis." },
    "portfolio_status": { "zh": "当前持仓风险评估", "en": "Portfolio risk check." },
    "reflection": { "zh": "AI的一句话反思", "en": "Short reflection." }
  },
  "actions": [
    {
      "symbol": "SOL",
      "action": "open_long",
      "leverage": 3,
      "position_size_usd": 1000,
      "entry_reason": {
        "zh": "发现鲸鱼在$135大量吸筹，且资金费率为负，存在轧空可能...",
        "en": "Whale accumulation detected at $135 with negative funding..."
      },
      "exit_plan": {
        "take_profit": 150,
        "stop_loss": 130,
        "invalidation": { "zh": "...", "en": "..." }
      }
    }
  ]
}
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

            return (f"RSI={m.get('rsi_14', 50):.1f} | ADX={m.get('adx_14', 0):.1f} | "
                    f"VolRatio={m.get('vol_ratio_20', 1):.1f}x | VolZ={m.get('vol_zscore_20', 0):.2f} | "
                    f"NATR={m.get('natr_percent', 0):.2f}% | Rank={m.get('price_rank_20', 50):.0f}% | "
                    f"Wick:Up={m.get('upper_wick_ratio',0)*100:.0f}%/Down={m.get('lower_wick_ratio',0)*100:.0f}% | "
                    f"BBW={m.get('bb_width', 0):.3f} | Trend={m.get('bb_trend', 'FLAT')} | Funding={m.get('funding_rate', 0)*100:.4f}% | "
                    f"Stars: Buy={m.get('buy_stars',0)}/Sell={m.get('sell_stars',0)}")

        # Build Context String
        ctx = "=== ETHEREUM (ETH) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        ctx += f"- Sentiment Score: 24h={eth_stat_24h.get('sentiment_score', 0):.2f} / 7d={eth_stat_7d.get('sentiment_score', 0):.2f}\n"
        ctx += f"- Token Net Flow: 24h={eth_stat_24h.get('token_net_flow', 0):,.1f} / 7d={eth_stat_7d.get('token_net_flow', 0):,.1f} ETH\n"
        ctx += f"- Stablecoin Net Flow: 24h=${eth_stat_24h.get('stablecoin_net_flow', 0):,.0f} / 7d=${eth_stat_7d.get('stablecoin_net_flow', 0):,.0f}\n"
        ctx += f"- Technicals: {fmt_tech(eth_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs Dropped ${eth_liq_long:,.0f} / Shorts Dropped ${eth_liq_short:,.0f}\n"
        
        ctx += "\n=== SOLANA (SOL) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        ctx += f"- Sentiment Score: 24h={sol_stat_24h.get('sentiment_score', 0):.2f} / 7d={sol_stat_7d.get('sentiment_score', 0):.2f}\n"
        ctx += f"- Token Net Flow: 24h={sol_stat_24h.get('token_net_flow', 0):,.1f} / 7d={sol_stat_7d.get('token_net_flow', 0):,.1f} SOL\n"
        ctx += f"- Stablecoin Net Flow: 24h=${sol_stat_24h.get('stablecoin_net_flow', 0):,.0f} / 7d=${sol_stat_7d.get('stablecoin_net_flow', 0):,.0f}\n"
        ctx += f"- Technicals: {fmt_tech(sol_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs Dropped ${sol_liq_long:,.0f} / Shorts Dropped ${sol_liq_short:,.0f}\n"
        
        ctx += "\n=== BITCOIN (BTC) CONTRACT DATA ===\n"
        ctx += f"- Technicals: {fmt_tech(btc_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs Dropped ${btc_liq_long:,.0f} / Shorts Dropped ${btc_liq_short:,.0f}\n"
        ctx += f"- Note: Focus on Squeeze potential via Liquidation Pain + Funding Rates.\n"
        
        ctx += "\n=== BNB CHAIN (BNB) CONTRACT DATA ===\n"
        ctx += f"- Technicals: {fmt_tech(bnb_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs Dropped ${bnb_liq_long:,.0f} / Shorts Dropped ${bnb_liq_short:,.0f}\n"
        
        ctx += "\n=== DOGECOIN (DOGE) CONTRACT DATA ===\n"
        ctx += f"- Technicals: {fmt_tech(doge_market)}\n"
        ctx += f"- Liquidation Pain (24h): Longs Dropped ${doge_liq_long:,.0f} / Shorts Dropped ${doge_liq_short:,.0f}\n"
        
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
    snapshot_path = BASE_DIR / "global_onchain_news_snapshot.json"
    if not snapshot_path.exists():
        return "No news data available."
        
    try:
        with open(snapshot_path, "r") as f:
            data = json.load(f)
            
        # 1. News - Collect from all available sources
        news_dict = data.get("news", {})
        all_news = []
        
        # Calendar (Economic Data) - High Priority
        calendar_news = news_dict.get("calendar", {}).get("items", [])
        calendar_str = ""
        if calendar_news:
            calendar_str = "Economic Calendar (This Week):\n"
            for item in calendar_news[:5]:
                calendar_str += f"- {item.get('title')} [{item.get('published')}]\n"
        
        # General News
        for source_key in ["macro", "bitcoin", "ethereum", "general"]:
            source_news = news_dict.get(source_key, {}).get("items", [])
            all_news.extend(source_news[:3])  # Take top 3 from each source
        
        news_str = "Latest News:\n"
        if all_news:
            for item in all_news[:8]:  # Show max 8 total general news
                news_str += f"- {item.get('title')} ({item.get('published', 'N/A')})\n"
        else:
            news_str += "No recent news available.\n"
            
        # Combine Calendar + News
        final_news_context = f"{calendar_str}\n{news_str}" if calendar_str else news_str
            
        # 3. Fear & Greed
        fng = data.get("fear_greed", {}).get("latest") or {}
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
            res = requests.get(url, timeout=5).json()
            
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

def validate_and_enforce_decision(decision, market_summary, daily_context, fear_index, executor):
    """
    Risk Management Layer (The "Supervisor").
    Sanitizes and overrides AI decisions based on hard rules.
    """
    if not decision or "actions" not in decision:
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
    
    # --- 3. PROCESS ACTIONS ---
    for action in decision["actions"]:
        symbol = action.get("symbol")
        act_type = action.get("action")
        try:
            size_usd = float(str(action.get("position_size_usd", 0)).replace('$', '').replace(',', ''))
        except ValueError:
            print(f"⚠️ Failed to parse size_usd: {action.get('position_size_usd')}, defaulting to 0")
            size_usd = 0.0
        
        if act_type == "hold":
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
            
            # D. Mandatory Stop Loss
            exit_plan = action.get("exit_plan", {})
            sl = exit_plan.get("stop_loss")
            if not sl or sl == "None":
                action["exit_plan"]["stop_loss"] = "Dynamic: 5% from entry (Auto-Enforced)"
                print(f"🛡️ RISK: Enforced mandatory Stop Loss for {symbol}")
                
            validated_actions.append(action)
            current_positions += 1
    
    decision["actions"] = validated_actions
    return decision

def run_agent():
    print("🤖 Activating Agent Dolores (Whale Edition)...")
    
    # Initialize Executor (Shadow Mode by default)
    # TODO: Set shadow_mode=False via env var for REAL TRADING later
    executor = OKXExecutor()
    
    # 1. Load Qlib Payload (Optional now, if missing we proceed with partial data)
    qlib_payload = "{}"
    if PAYLOAD_PATH.exists():
        with open(PAYLOAD_PATH, "r") as f:
            qlib_payload = f.read()

    # Load Fear & Greed Index for Validation
    fear_index = 50 # Default Neutral
    try:
        snapshot_path = BASE_DIR / "global_onchain_news_snapshot.json"
        if snapshot_path.exists():
            with open(snapshot_path, "r") as f:
                snap_data = json.load(f)
                fng_val = snap_data.get("fear_greed", {}).get("latest", {}).get("value")
                if fng_val is not None:
                    fear_index = float(fng_val)
    except Exception as e:
        print(f"⚠️ Failed to load Fear Index: {e}")
        
    # 2. Prepare Prompt
    portfolio_state = get_portfolio_state(executor)
    news_context = get_news_context()
    
    # NEW: Get Whale Data
    whale_context, whale_data_obj = get_whale_data()
    print(f"🐋 Whale Data Loaded:\n{whale_context[:200]}...") # Debug print
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    final_prompt = SYSTEM_PROMPT.replace("{{CURRENT_TIMESTAMP}}", current_time)
    final_prompt = final_prompt.replace("{{QLIB_JSON_PAYLOAD}}", qlib_payload)
    final_prompt = final_prompt.replace("{{WHALE_CONTEXT}}", whale_context)
    
    # Add Daily Context + MEMORY INJECTION
    memory_context = memory.get_recent_performance()
    daily_context = get_daily_context_summary()
    
    # Combined Context
    combined_context = f"{daily_context}\n\n{memory_context}"
    final_prompt = final_prompt.replace("{{DAILY_CONTEXT}}", combined_context)
    
    final_prompt = final_prompt.replace("{{PORTFOLIO_STATE_JSON}}", portfolio_state)
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
                    temperature=0.1,
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
                if attempt < MAX_RETRIES - 1:
                    print(f"🔄 Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e # Final attempt failed
        
        # Validate & Enforce
        decision = validate_and_enforce_decision(decision, {}, daily_context, fear_index, executor)
            
        print("\n💡 Dolores' Decision:")
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        
        # === NEW: EXECUTION LAYER ===
        actions = decision.get("actions", [])
        for act in actions:
            symbol = act.get("symbol")
            action_type = act.get("action")
            try:
                amount = float(str(act.get("position_size_usd", 0)).replace('$', '').replace(',', ''))
            except ValueError:
                amount = 0.0
                
            leverage = act.get("leverage", 1)
            
            exit_plan = act.get("exit_plan", {})
            sl = exit_plan.get("stop_loss")
            tp = exit_plan.get("take_profit")
            
            # Filter for actual executable trade actions
            is_trade = any(keyword in action_type for keyword in ["open_", "close"])
            
            if is_trade and action_type != "REJECTED":
                print(f"\n🚀 Triggering Executor for {symbol} ({action_type})...")
                executor.execute_trade(symbol, action_type, amount, leverage, stop_loss=sl, take_profit=tp)
                
                # LOG TO MEMORY
                try:
                    sym_lower = symbol.lower()
                    market_snapshot = whale_data_obj.get(sym_lower, {}).get('market', {})
                    entry_reason = act.get('entry_reason', {})
                    # Add reason string for text logs
                    reason_txt = entry_reason.get('en', 'Driven by whale accumulation.')
                    
                    memory.log_trade(symbol, action_type, amount, entry_reason, market_snapshot)
                    
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
