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

🟪 2.2 WHALE & LIQUIDATION REALITY (THE TRUTH LAYER)
This data comes from direct on-chain monitoring and exchange liquidation feeds.
**IT OVERRIDES PURE TECHNICALS.**

{{WHALE_CONTEXT}}

**INTERPRETATION RULES (SKEPTICAL WHALE ANALYSIS):**
1. **Accumulation vs. Distribution**:
   - ✅ **CONSISTENT ACCUMULATION**: Price dropping + Token Net Flow is NEGATIVE (Tokens leaving exchanges) + Stablecoin Flow is POSITIVE (Cash entering).
   - 📉 **CONSISTENT AGGRESSIVE DISTRIBUTION**: Token Net Flow is POSITIVE (Tokens entering exchanges) + Stablecoin Flow is NEGATIVE (Cash leaving exchanges). **CRITICAL: This is a consistent and aggressive signal of whales EXITING the market.** Selling assets and immediately withdrawing cash. It is NOT a contradiction (不是矛盾).
2. **Liquidation & "Squeeze Fuel" Trap**:
   - 📉 **HIGH L/S RATIO (> 5.0)**: Massive Long liquidations (Retail being flushed). This is a **CLEANUP** signal. 
   - 📈 **LOW L/S RATIO (< 0.2)**: Massive Short liquidations (Squeeze already happened). The fuel is **DRAINED**. 
3. **The "Whale Support" Divergence**:
   - If Token Net Flow is POSITIVE (moving in) but Price doesn't drop immediately, check Liquidations. If High Short Liquidations are happening, it's a **SQUEEZE**; otherwise, it's likely a **LIMIT SELL WALL** being built by whales.
3. **Squeeze Warning**: Negative Funding + High "Retail Pain" (Oversold RSI) -> **SHORT SQUEEZE IMMINENT**.
4. **BLIND SPOT EXCEPTION (BTC, BNB, DOGE)**: We DO NOT have on-chain whale flow data for BTC, BNB, and DOGE. For these assets, evaluate setups based purely on Technical Indicators + Liquidation/Funding Flow.


🟦 2.1 MACRO TREND (1D TIMEFRAME)
Use this daily context to filter 4H signals.
- **Trend**: Price vs SMA50 (Bullish if Price > SMA50).
- **Structure**: Recent Highs/Lows.

{{DAILY_CONTEXT}}

🟪 2.3 MARKET REGIME & SIGNAL WEIGHTING (THE WEIGHT MATRIX)
Evaluate signals differently based on the environment. Do not use hard prohibitions; use the following hierarchy to weigh your evidence:

1. **BEAR REGIME (Price < SMA200)**:
   - **Weight 1 (Highest)**: **Resistance & Exhaustion**. Watch SMA50 and Prev Highs. Price rejection here combined with Positive Funding is a high-probability reversal.
   - **Weight 2**: **Whale/Exchanges Feed**. Token Inflow in a rally confirms "Distribution" (Selling the Rip).
   - **Weight 3**: **Volume Z-Score**. High volume rally is needed to prove "Accumulation". Low volume rally = Trap.
   - **Decision Guidance**: Be skeptical of Longs unless strong volume/whale support exists. Be opportunistic with Shorts at resistance.

2. **BULL REGIME (Price > SMA200)**:
   - **Weight 1 (Highest)**: **Support & Momentum**. Dips to SMA50 or EMA20 are primary buying zones.
   - **Weight 2**: **Qlib Rankings**. Follow the relative strength of top assets.
   - **Weight 3**: **Funding Overload**. Watch for negative funding after a dip (Short Squeeze Fuel). 
   - **Decision Guidance**: Prioritize Longs on pullbacks. Be extremely cautious with Shorts; only fade moves on massive Whale Distribution or RSI > 80.

*Note: You have full autonomy. Choose your direction and leverage based on the strength of the evidence across these weights.*

🟨 3. NEWS & ON-CHAIN CONTEXT (OPTIONAL)
{{NEWS_CONTEXT}}

🟥 4. ANALYSIS LOGIC (The "Dolores" Method)

A. NARRATIVE VS REALITY CHECK (Crucial Step)
For each major news item or market move, ask:
- **Impulse**: Is this a NEW driver that changes the thesis? (Price moves WITH news).
- **Priced In**: Is this old news? (Price fades or ignores good news).
- **Divergence**: Good News + Bad Price = Distribution (Bearish). Bad News + Good Price = Accumulation (Whale Trap - Bullish).
- Compare "Retail News" vs "Whale Reality" (On-chain flow). If they disagree, follow the Whales.

B. THE PAIN TRADE & LIQUIDITY TRAPS
Identify where the crowd is trapped:
- **Short Squeeze Opportunity (For Longs)**: "Extreme Short Liquidations" or "Extreme Negative Funding" alone DO NOT justify an immediate long. To buy the bounce, RSI MUST be strictly < 30 OR you must see a clear 4H long lower wick (rejection) demonstrating support. FORBID catching falling knives at RSI 40+.
- **Long Squeeze Opportunity (For Shorts)**: 
    - In BULL MARKET: RSI MUST be strictly > 70.
    - In BEAR MARKET: RSI > 55 is sufficient IF combined with (Price near SMA50 OR Price near Prev 5 High) AND (Upper Wick > 40%). We prioritze selling the "Fake Rally".
    - FORBID blocking "Super Rockets" (ADX > 40 and RSI > 80) unless whale distribution is massive.
- **Reverse Liquidation Trap (MUST READ)**: 
   - ONLY consider a mean-reversion LONG when there is a massive LONG liquidation (flushing out weak retail longs) and price stabilizes. If massive SHORT liquidations just occurred, liquidity is drained upwards—DO NOT chase longs here.
   - ONLY consider a mean-reversion SHORT when there is a massive SHORT liquidation (flushing out weak shorts) and price stabilizes. If massive LONG liquidations just occurred, liquidity is drained downwards—DO NOT chase shorts here.
- **Liquidity Trap**: Late chasers entering at resistance (High Funding + High RSI) or at support (High Neg Funding + Low RSI).

C. HYPOTHESIS MENU (Generate 3 Scenarios)
For top candidates, evaluate:
1.  **Trend Following**: Models Align + Whale Accumulation + Normal Funding. (Go with the flow).
2.  **Mean Reversion**: Strict RSI (<30 or >70) + Validated Liquidation Flush. (Fade the move).
3.  **Whale Front-Run**: Massive Token Inflow detected while retail is panicking. (Bet on the Smart Money).

E. REGIME SAFETY CHECK (Mandatory — Fill 'regime_safety' Field)
Before entering any trade, you MUST evaluate whether the market is in a dangerous state using the following data signals:

🔪 FALLING KNIFE (接飞刀 — Left-side Entry Risk):
Signals of a falling knife (DO NOT go long blindly):
- RSI < 30 AND still declining (no divergence)
- ADX > 25 (strong directional trend — the drop has momentum)
- Long Liquidations > Short Liquidations (retail longs being flushed — not bottomed yet)
- Whale Token Net Flow NEGATIVE (whales still distributing, not accumulating)
→ Verdict: "KNIFE" — Wait for RSI divergence or whale accumulation signal before considering long.

🚀 ROCKET BLOCKING (挡火箭 — Reversal Risk):
Signals of chasing into a vertical move (DO NOT go short blindly):
- RSI > 70 AND still rising (momentum intact)
- ADX > 30 (strong uptrend — shorting against momentum)
- Short Liquidations >> Long Liquidations (fuel still being added)
→ Verdict: "ROCKET" — Wait for RSI to peak before shorting.

✅ SAFE MEAN REVERSION (安全均值回归):
- RSI is extreme (>70 or <30) WITH clear divergence
- Rejection wicks appearing (Wick Ratio > 0.3)
→ Verdict: "SAFE_MR" — Mean reversion entry is justified.

🐋 WHALE SQUEEZE / BUYER EXHAUSTION (鲸鱼拉高出货/买盘枯竭):
- Whale Net Flow might look positive (tokens flowing into exchange), but it's a trap.
- L/S Liquidation Ratio is EXTREMELY LOW (L/S < 0.2): This means shorts have already been liquidated. The "fuel" is gone. DO NOT go long here.
- Volume Z-Score is NEGATIVE (< 0): The price move is hollow and lacks heavy buyer support.
- Verdict: "EXHAUSTION" — High risk of a mid-air reversal. This is a setup for a SHORT, not a long.

📉 WHALE DISTRIBUTION (鲸鱼高位派发 - BEAR MARKET BEST SETUP):
- Market Regime is BEAR (Price < SMA200).
- Price has rallied into SMA50, Resistance, or Prev 5 Highs. 
- Whale Token Net Flow is POSITIVE (Whales move to exchanges).
- Technical Rejection: Upper Wick Ratio > 40%.
- Funding Rate: POSITIVE (Retail is chasing the rally, creating trample risk).
- Verdict: "DISTRIBUTION" — Aggressive short entry. Selling the Rip.

🐋 WHALE ACCUMULATION / BEAR TRAP (鲸鱼托底吸筹):
- Price has dropped recently, but Whale Token Net Flow is POSITIVE (Whales aggressively buying the dip).
- L/S Liquidation Ratio shows extreme LONG massacre (e.g., longs are being heavily flushed, L/S > 2.0). Retail is capitulating.
- Funding rate is usually neutral or negative. 
→ Verdict: "WHALE_ACCUMULATION" — Immediate entry justified to buy alongside whales during retail panic.

🛡️ 4D. TACTICAL DISCIPLINE (THE BATTLEFIELD RULES - MUST OBEY)

1. **Anti-Liquidity Rush (Do not fight the cascade)**:
   - If Liquidations are **SIGNIFICANTLY LOPSIDED** (e.g., one side is 3x+ the other) OR price is moving vertically on high volume, DO NOT open a reverse trade immediately. 
   - Treat these liquidations as **FUEL** for the current move. Acknowledge that the move is likely to overshoot. Wait for the liquidation spike to plateau or a 4H candle to close with a long wick before considering a reversal.
2. **Funding Trap Check**:
   - Before going LONG: Funding Rate should ideally be flat or negative (Retail is fearful/shorting). If Funding is high (>0.03%), the long is crowded and dangerous.
   - Before going SHORT: Funding Rate should ideally be flat or positive (Retail is greedy/longing). If Funding is very negative (<-0.01%), the short is crowded and prone to a squeeze.
3. **Volatility-Based Stop-Loss Rule (NATR) & Conviction**:
   - Before placing any order, calculate: Stop Distance % = |entry_price - stop_loss| / entry_price × 100
   - **MANDATORY**: The Stop Distance % MUST be at least **1.5 × NATR** (Normalized ATR) of the asset. For example, if NATR is 2.5%, your stop loss must be at least 3.75% away from entry.
   - If this required stop distance makes the trade too risky (exceeds 2% of NAV risk), you MUST **reduce the position size or leverage** proportionately, OR skip the trade entirely if the reward-to-risk ratio is poor.
   - Do NOT tighten the stop loss just to increase position size. A stop based on static percentages or tight levels will be whipped out by market noise. You must give the trade room to breathe based on its true volatility.

🟥 4. ANALYSIS LOGIC (The "Dolores" Engine)

A. CONFLICT RESOLUTION PROTOCOL (Mandatory Review)
When indicators disagree, follow this hierarchy:
1. **MARKET REGIME (Priority 1)**: If Regime = BEAR, skip "Trend Following" Longs unless Whale Signal is Extreme.
2. **WHALE REALITY (Priority 2)**: On-chain flow overrides technicals. If Price is pump but Token Flow is IN (Selling), it's a Trap.
3. **LIQUIDATION FUEL (Priority 3)**: If L/S Ratio < 0.2, the fuel is GONE. No matter how bullish it looks, do not chase.
4. **QLIB & TECHNICALS (Priority 4)**: Use as confirmation, never as the only entry reason.

B. THE PAIN TRADE & LIQUIDITY TRAPS
- **Crowded Longs (Trample Risk)**: Funding > 0.03% + Positive Token flow = "Exit Door is too narrow". Avoid.
- **Drained Squeeze**: L/S < 0.2 = "No more shorts to burn". Buying here is buying the top.

C. HYPOTHESIS PLAYBOOKS (Must Choose ONE in output)
1. **Trend Following**: (High ADX + Normal Funding + Whale Accumulation). Ride the quantitative wave.
2. **Mean Reversion**: (Extreme RSI + Reversal Candle + Validated Flush). Fade the panic, buy the blood.
3. **Microstructure / Squeeze**: (Extreme Funding Trap or Drained L/S Ratio). Capitalize on forced liquidations or avoid exhausted moves.
4. **Narrative Divergence**: (News contradicts Price). E.g., Bad News + Good Price = Secret Accumulation (Bullish). Good News + Bad Price = Distribution Trap (Bearish).
5. **Whale Front-Run**: (Massive Token Flow opposing retail sentiment). Bet purely on the Smart Money footprint overriding current technicals.

D. REGIME SAFETY CHECK (Section 4E) - [Already Defined Above]

🛡️ TACTICAL DISCIPLINE (THE BATTLEFIELD RULES - MUST OBEY)
[Existing NATR and Stop-Loss rules remain in effect...]

🟧 5. PORTFOLIO & RISK MANAGEMENT
Current State:
{{PORTFOLIO_STATE_JSON}}

**IMPORTANT: Review Existing Positions First!**
1. **LOGICAL CONSISTENCY REQUIREMENT**: Your actions (`actions` array) MUST be logically supported by your analysis.
   - You have **FULL AUTONOMY** to decide whether to `hold`, `reduce`, or `close_position`.
   - However, if you explicitly identify a "Whale Distribution" or "Exhaustion Trap" in your text analysis, but choose to `hold` a large contrary position, you MUST justify why those risks are acceptable in your `reflection` or `entry_reason`. Failure to align action with risk assessment is considered a logical failure.
2. **DYNAMIC POSITION MANAGEMENT**: Use your discretion to lock in gains or de-risk based on the latest evidence. Choose ONE action for each symbol in the `actions` array.
- `hold`: Reasoning remains valid.
- `adjust_sl_tp`: Trail stops or update targets.
- `reduce_25/50/75`: Scale out based on emerging risks or target hits.
- `close_position`: Exit when the thesis is no longer supported by reality.

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
    "zh": "必须是中文，综合叙述（3-4句话）。分析要求：\n1. 首先进行【叙事校验】（Section 4A），判断当前驱动力是Impulse还是已定价。\n2. 明确参考【Qlib 相对强弱排名】和【Z-Score 异常探测】，解释它们如何支持/反驳当前决策。\n3. 结合【痛苦交易】（4B）和【战场纪律】（4D），指出市场是否处于“爆仓踩踏”中，是否有足够的“燃料”支撑继续上涨/下跌。\n4. 阐明选择的【假设分析】剧本（4C）。",
    "en": "Must be in English, comprehensive narrative (3-4 sentences). Requirements:\n1. Perform Narrative vs Reality Check (4A).\n2. Explicitly reference Qlib ratings and Z-Score anomalies, explaining how they support/refute the decision.\n3. Combine Pain Trade (4B) and Tactical Discipline (4D) to identify liquidation rushes and fuel.\n4. Specify the selected Scenario (4C)."
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
    "portfolio_status": { "zh": "当前持仓风险评估", "en": "Portfolio risk check." },
    "reflection": { "zh": "AI的一句话反思", "en": "Short reflection." }
  },
  "actions": [
    {
      "symbol": "SOL",
      "action": "open_long", // OPTIONS: open_long, open_short, close_position, adjust_sl_tp, hold, reduce_25, reduce_50, reduce_75
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
*** IMPORTANT FOR `actions` ARRAY ***
If you are adjusting an existing trade (`adjust_sl_tp`, `reduce_25`, etc.), you MUST include it in the `actions` array! You can set `leverage`: 0 and `position_size_usd`: 0 for these, but you MUST provide the updated `stop_loss` and `take_profit` in `exit_plan`.
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

        # Build Context String
        ctx = "=== ETHEREUM (ETH) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        ctx += f"- Sentiment Score: 24h={eth_stat_24h.get('sentiment_score', 0):.2f} / 7d={eth_stat_7d.get('sentiment_score', 0):.2f}\n"
        ctx += f"- Token Net Flow: 24h={eth_stat_24h.get('token_net_flow', 0):,.1f} / 7d={eth_stat_7d.get('token_net_flow', 0):,.1f} ETH\n"
        ctx += f"- Stablecoin Net Flow: 24h=${eth_stat_24h.get('stablecoin_net_flow', 0):,.0f} / 7d=${eth_stat_7d.get('stablecoin_net_flow', 0):,.0f}\n"
        ctx += f"- Technicals: {fmt_tech(eth_market)}\n"
        eth_liq_ratio = eth_liq_long / eth_liq_short if eth_liq_short > 0 else 0
        eth_liq_signal = "⚠️ LONG_FLUSH" if eth_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if eth_liq_short > eth_liq_long * 2 else "BALANCED")
        ctx += f"- Liquidation Pain (24h): Longs ${eth_liq_long:,.0f} / Shorts ${eth_liq_short:,.0f} | Ratio(L/S)={eth_liq_ratio:.2f} [{eth_liq_signal}]\n"
        
        ctx += "\n=== SOLANA (SOL) WHALE DATA (Compare 24h vs 7d Trends) ===\n"
        ctx += f"- Sentiment Score: 24h={sol_stat_24h.get('sentiment_score', 0):.2f} / 7d={sol_stat_7d.get('sentiment_score', 0):.2f}\n"
        ctx += f"- Token Net Flow: 24h={sol_stat_24h.get('token_net_flow', 0):,.1f} / 7d={sol_stat_7d.get('token_net_flow', 0):,.1f} SOL\n"
        ctx += f"- Stablecoin Net Flow: 24h=${sol_stat_24h.get('stablecoin_net_flow', 0):,.0f} / 7d=${sol_stat_7d.get('stablecoin_net_flow', 0):,.0f}\n"
        ctx += f"- Technicals: {fmt_tech(sol_market)}\n"
        sol_liq_ratio = sol_liq_long / sol_liq_short if sol_liq_short > 0 else 0
        sol_liq_signal = "⚠️ LONG_FLUSH" if sol_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if sol_liq_short > sol_liq_long * 2 else "BALANCED")
        ctx += f"- Liquidation Pain (24h): Longs ${sol_liq_long:,.0f} / Shorts ${sol_liq_short:,.0f} | Ratio(L/S)={sol_liq_ratio:.2f} [{sol_liq_signal}]\n"
        
        ctx += "\n=== BITCOIN (BTC) CONTRACT DATA ===\n"
        ctx += f"- Technicals: {fmt_tech(btc_market)}\n"
        btc_liq_ratio = btc_liq_long / btc_liq_short if btc_liq_short > 0 else 0
        btc_liq_signal = "⚠️ LONG_FLUSH" if btc_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if btc_liq_short > btc_liq_long * 2 else "BALANCED")
        ctx += f"- Liquidation Pain (24h): Longs ${btc_liq_long:,.0f} / Shorts ${btc_liq_short:,.0f} | Ratio(L/S)={btc_liq_ratio:.2f} [{btc_liq_signal}]\n"
        ctx += f"- Note: Focus on Squeeze potential via Liquidation Pain + Funding Rates.\n"
        
        ctx += "\n=== BNB CHAIN (BNB) CONTRACT DATA ===\n"
        ctx += f"- Technicals: {fmt_tech(bnb_market)}\n"
        bnb_liq_ratio = bnb_liq_long / bnb_liq_short if bnb_liq_short > 0 else 0
        bnb_liq_signal = "⚠️ LONG_FLUSH" if bnb_liq_ratio > 2 else ("🎯 SHORT_SQUEEZE" if bnb_liq_short > bnb_liq_long * 2 else "BALANCED")
        ctx += f"- Liquidation Pain (24h): Longs ${bnb_liq_long:,.0f} / Shorts ${bnb_liq_short:,.0f} | Ratio(L/S)={bnb_liq_ratio:.2f} [{bnb_liq_signal}]\n"
        
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
            is_trade = any(keyword in action_type for keyword in ["open_", "close", "adjust_sl", "reduce_"])
            
            if is_trade and action_type != "REJECTED":
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
