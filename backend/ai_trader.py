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
from notifier import notify_trade_execution, notify_rejection_alert, notify_cycle_summary, escape_html # Notification System

# Load environment variables
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Client
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL)
VERSION = "2026.03.25.1225" # Code version for tracking deployment status

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
                
                # New: Include Red Team Audit and Confidence
                red_team = latest_decision.get("red_team_audit", {}).get("en", "N/A")
                confidence = latest_decision.get("confidence_probability", "N/A")
                
                if reflection or red_team != "N/A":
                    summary += f"[LATEST AI CYCLE: {latest_time}]\n"
                    summary += f"Previous Confidence: {confidence}%\n"
                    summary += f"Previous Reflection (ZH): {latest_decision.get('context_analysis', {}).get('reflection', {}).get('zh', 'N/A')}\n"
                    summary += f"Previous Reflection (EN): {reflection}\n"
                    summary += f"Previous Red Team Audit (ZH): {latest_decision.get('red_team_audit', {}).get('zh', 'N/A')}\n"
                    summary += f"Previous Red Team Audit (EN): {red_team}\n\n"
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
                        
                        rationale_zh = t['reason'].get('zh', '') if isinstance(t.get('reason'), dict) else ""
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
                            
                        summary += f"    Rationale (ZH): {rationale_zh[:200]}\n"
                        summary += f"    Rationale (EN): {rationale_en[:200]}\n\n"
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

Role: Professional Multi-Coin Portfolio Manager.
Capabilities:
- Analyze Basket-wide Market Structure (BTC, ETH, SOL, BNB, DOGE).
- Interpret Sentiment Data (Funding Rate, Open Interest, Z-Scores) across all 5 assets.
- **INTEGRATE WHALE INSIGHTS**: Process Token Flow, Stablecoin Flow, and Liquidation Pain.
- Detect Pain Trades (Squeezes, Crowded Trades) using On-Chain evidence.
- Manage Risk (Position Sizing, Stop Loss, Portfolio Heat).

Goal: Achieve stable risk-adjusted returns through diversification. Detect "Whale Traps" and multi-coin opportunities. Do not fixate on a single asset.

🟧 1. CURRENT TIME
Current Timestamp: {{CURRENT_TIMESTAMP}}

🟦 2. MARKET INPUTS (QLIB + SENTIMENT)
You will receive a JSON payload containing:
- `qlib_score`: Relative strength prediction (Higher = Stronger).
- `rank`: 1 (Best) to 5 (Worst).
- `market_data`: 
    - **Technical**: RSI (14), MACD Hist, ATR, Bollinger Width, Momentum.
    - **Sentiment**: Funding Rate, Funding Z-Score, OI Change, OI RSI.
    - **Volatility**: Normalized ATR (natr_14).

{{QLIB_JSON_PAYLOAD}}

🟪 2.2 WHALE & LIQUIDATION REALITY (数据实况)
This data comes from direct on-chain monitoring and exchange liquidation feeds.

DATA GLOSSARY (指标释义):
- [持仓L/S比]: 大户账户数多空比与持仓量多空比。反映资金博弈分布。
- [24h爆仓量分布]: 过去24小时内多单与空单的强平金额。
- [爆仓多空比]: 多单爆仓金额 / 空单爆仓金额。高于1表示多头受压显著。
- [技术指标详情]: 包含 [均线乖离率]、[RSI/ADX 状态]、[上影线/下影线比率]、[波动率 NATR] 等。
- [鲸鱼代币流向]: 巨鲸往交易所充提**加密资产(如ETH/SOL)**的净值。(仅限ETH/SOL)
  ⚠️核心逻辑（标准化）⚠️：现在的数值已标准化。**Token Flow 为正(+) = 提币囤货/流出（看涨）**，数值为负(-) = 充币抛售/流入（看跌）。
- [鲸鱼资金流向]: 巨鲸往交易所充提**稳定币(USDT/USDC)**的净值。(仅限ETH/SOL)
  ⚠️核心逻辑（标准化）⚠️：现在的数值已标准化。**Stablecoin Flow 为正(+) = 流入交易所准备抄底（看涨）**，数值为负(-) = 资金离场（看跌）。
- 对于 BTC/BNB/DOGE，由于尚未接入链上监控，流向均显示 N/A，请忽略流向，重点分析其 [交易所情绪] (OKX Top Trader Sentiment) 和 [24h爆仓量分布]。

{{WHALE_CONTEXT}}


🟦 2.1 MACRO TREND (1D TIMEFRAME)
Use this daily context to filter 4H signals.
- **Trend**: Price vs SMA50 (Bullish if Price > SMA50).
- **Structure**: Recent Highs/Lows.

{{DAILY_CONTEXT}}

 3. NEWS & ON-CHAIN CONTEXT (OPTIONAL)
{{NEWS_CONTEXT}}

🟥 4. ANALYSIS FRAMEWORK (Execute in Order)

**4A. NARRATIVE VS REALITY CHECK (Do this FIRST)**
For each major market move or news item, ask:
- **Impulse**: Is this a NEW driver that changes the thesis? (Price moves WITH the news/data)
- **Priced In**: Is this old news? (Price fades or ignores good news = distribution)
- **Divergence**: Good data + falling price = Hidden Accumulation (Bullish). Bad data + rising price = Distribution (Bearish).

**4B. THE PAIN TRADE (痛苦交易 - 定位陷阱)**
Who is trapped and where is the forced exit?
- Look at [持仓L/S比]: 哪一方目前最拥挤？
- Look at [24h爆仓量分布]: 哪一方正在遭受强平痛苦？
- If crowded long + funding high + price stalling → ⚠️ LONG SQUEEZE DANGER (多头挤压风险)
- If crowded short + funding negative + price holding → 🚀 SHORT SQUEEZE OPPORTUNITY (空头轧空机会)
- If longs already flushed (high liq ratio) → 抛压可能衰竭，转折点接近
- If shorts already squeezed (low liq ratio) → 冲高动能可能衰竭，回调接近

**4C. GENERATE 3 SCENARIOS — Then Pick the Best**
Before committing, explicitly consider all three:
1. **TREND_FOLLOWING**: High Qlib Score + Positive Momentum + Normal Funding → go with the flow.
   - Trigger: Price above SMA50, RSI 45-65, whale flow in same direction, funding near 0%.
2. **MEAN_REVERSION**: Extreme technical or sentiment readings → fade the move.
   - Trigger: RSI >75 or <25, extreme funding (>0.05% or <-0.05%), reversal candle patterns.
3. **MICROSTRUCTURE_SQUEEZE / WHALE_FRONT_RUN**: Passive liquidity event or institutional flow divergence.
   - Squeeze Trigger: Crowded side (per 持仓L/S比) + adverse funding + price holding key level → forced covering incoming.
   - Whale Trigger: On-chain flow contradicts price action (e.g., tokens leaving exchange while price drops = accumulation).

Score each scenario by: (Signal Strength) × (Data Confluence) × (Risk/Reward).
Choose the highest-scoring one. **Explicitly state why you rejected the other two.**

4. **ALPHA RRR RULE (RRR > 1.5)**: Every `open` action MUST have a projected Profit targets at least 1.5x larger than the Stop Loss distance.
5. **2% NAV RISK CAP**: Size trades so `(Size * SL%) <= (Total Equity * 0.02)`. 
6. **NO NESTED QUOTES**: Use ONLY single quotes or brackets `()` inside JSON string fields. **NEVER use double quotes "" inside a string.** 
7. **JSON ONLY**: Output ONLY the raw JSON. No markdown backticks, no introductions.

**4E. RED TEAM AUDIT**
Before finalizing, perform a **Red Team Audit** on your own conclusion:
1. **The "Bet" Test**: If you had to bet 50% of your own wealth on this trade, what information would make you hesitate? (Identify "Unknown Unknowns").
2. **Red Team Mode**: If you were forced to argue the EXACT OPPOSITE position (e.g., if you are long, build the strongest Bear case), what evidence would you use? 
3. **Source De-coupling**: Evaluate the data points (Whale Flow, Funding, News) purely as numbers. Do not let a "famous" narrative or a large news headline bias you if the on-chain reality is neutral.
4. **Decision Swear Jar**: DO NOT use words like "Certain", "100%", "Definitely", "Impossible", "Everyone knows". Any use of these triggers a logic penalty.

HYPOTHESIS OPTIONS:
1. **TREND_FOLLOWING**: Ride the momentum based on flow and technicals.
2. **MEAN_REVERSION**: Trade reversals when price and data reach extremes.
3. **MICROSTRUCTURE_SQUEEZE**: Capitalize on liquidity traps and funding anomalies.
4. **NARRATIVE_DIVERGENCE**: When data contradicts price action (e.g., Hidden Accumulation).
5. **WHALE_FRONT_RUN**: Align with institutional flow.

🟧 5. PORTFOLIO & RISK MANAGEMENT
Current State:
{{PORTFOLIO_STATE_JSON}}

**THE PRIMARY MISSION: ACTIVE POSITION MAINTENANCE (MANDATORY FIRST)**
Before even thinking about new trades, you MUST address your current exposure.
1. **THE 1:1 CLEANSE RULE (MANDATORY)**: Every decision cycle, your first task is a per-asset audit.
   - **MAPPING REQUIREMENT**: For EVERY symbol listed in `{{PORTFOLIO_STATE_JSON}}`, you **MUST** provide a corresponding entry in the `portfolio_management` object. 
   - **ZERO OMISSION**: You are NOT allowed to skip any current holding. If you hold BTC, DOGE, BNB, or any other asset, it MUST be listed.
   - **ASSET-SPECIFIC DEFENSE**: 
     - For coins WITH whale data (ETH, SOL): Defend based on Flow + Technicals.
     - For coins WITHOUT whale data (BTC, DOGE, BNB): You **MUST** defend the position based on Technicals (RSI/ADX) + Liquidation Pain + Qlib Ranking. 
     - "Missing data" is NOT a reason to skip an action.
   - **ZERO TOLERANCE**: Failing to provide a matching action entry for ANY symbol in portfolio is a **LOGICAL INTEGRITY BREACH**.

2. **THE TRACKED ASSET AUDIT (MANDATORY)**:
   - Even if you don't hold them, you **MUST** evaluate the current state of ALL FIVE core assets: **BTC, ETH, SOL, BNB, DOGE**.
   - If an asset is NOT currently in your portfolio, it **MUST** appear in either `portfolio_management` (if you are opening a position) or `new_opportunities` (as `monitor`, `open_long`, or `open_short`).
   - You are not allowed to ignore SOL or DOGE just because you aren't trading them. Provide a brief `monitor` reason for each tracked asset not traded.

3. **THE SECONDARY MISSION: NEW ENTRIES (PRIVILEGED ACCESS)**:
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
    "zh": "必须是全中文，按以下结构分段阐述：\n1. [叙事校验]：判断当前驱动力是‘冲动驱动’还是‘已定价’，识别市场主旋律。\n2. [决策依据详情]：综合技术信号、宏观与链上数据、量化指标（Qlib/Z-Vol）的交叉验证。\n3. [痛苦交易]：分析强平头寸分布与多空比（L/S Ratio），识别市场是否处于‘盲目踩踏’或‘动能衰竭’阶段。\n4. [剧本选择]：明确 Section 4C 中的剧本及选择理由。",
    "en": "Must be in English, structured as follows:\n1. [Narrative Validation]: Impulse vs Priced-in.\n2. [Decision Details]: Cross-verification of Tech, Whale, and Quant signals.\n3. [Pain Trade]: Liquidation fuel and L/S Ratio analysis.\n4. [Scenario Selection]: Chosen Scenario (4C) and justification."
  },
  "confidence_probability": 75, /* Use a percentage 0-100% instead of absolute certainty. Admit your 25% uncertainty. */
  "red_team_audit": {
    "zh": "【强制要求全中文】强行站在对立面（红色突击队/红军审计），列出如果你的判断是错误的，最可能的反向理由是什么？哪些数据支撑反面结论？",
    "en": "Forced Contra-Argument: If your thesis is WRONG, what is the most likely reason? What data points support the opposite view?"
  },
  "hypothesis_scenario": "TREND_FOLLOWING | MEAN_REVERSION | MICROSTRUCTURE_SQUEEZE | NARRATIVE_DIVERGENCE | WHALE_FRONT_RUN",
  "contrary_signal_check": {
    "zh": "【要求全中文】列出目前最明显的冲突信号或潜在风险点，并合理解释为什么它们不会推翻你的交易结论。",
    "en": "List the most significant contrary signal or risk point and justify why it doesn't invalidate the trade."
  },
  "context_analysis": {
    "technical_signal": { 
        "zh": "【全中文】必须明确提及：1) 上/下影线比率 (Wick Ratio) 以判断抛压或托底力度; 2) RSI 与 ADX 的具体趋势状态; 3) 价格与均线的偏离度 (SMA Deviation)。", 
        "en": "【IMPORTANT】Must explicitly mention: 1) Upper/Lower Wick Ratio to judge selling pressure/support; 2) RSI & ADX status; 3) SMA deviation." 
    },
    "macro_onchain": { 
        "zh": "【全中文】必须明确提及：1) 过去 24 小时强平数据及多空强平比; 2) 巨鲸资金的净流入/流出情况; 3) 当前的资金费率状态。", 
        "en": "【IMPORTANT】Must explicitly mention: 1) 24h Liquidation Data & Long/Short Liquidation Ratio; 2) Whale Net Inflow/Outflow; 3) Funding Rate." 
    },
    "quantitative_analysis": { 
        "zh": "【全中文】分析 Qlib 排名靠前的币种及其 Qlib 分数的显著性，以及量价偏差（如成交量或费率的 Z-Score 异常）。", 
        "en": "Analyze Qlib top-ranked coins and Z-Score significance (statistical deviations in vol/funding)." 
    },
    "regime_safety": { 
        "zh": "【全中文必填】基于 Section 4B（痛苦交易）进行评估。最终给出明确的中文判断：‘接飞刀’ (KNIFE) / ‘挡火箭’ (ROCKET) / ‘安全均值回归’ (SAFE_MR) / ‘鲸鱼轧空’ (WHALE_SQUEEZE) / ‘鲸鱼托底’ (WHALE_ACCUMULATION)，并详细说明依据。", 
        "en": "【Required】Based on Section 4B (Pain Trade): 1) RSI/ADX/NATR current state; 2) Upper/Lower Wick Ratio; 3) Liquidation long/short ratio; 4) Whale net flow direction. Conclude with explicit verdict: KNIFE / ROCKET / SAFE_MR / WHALE_SQUEEZE / WHALE_ACCUMULATION and explain why." 
    },
    "portfolio_status": { "zh": "当前投资组合的风险评估（全中文）", "en": "Portfolio risk check." }
  },
  "portfolio_management": [
    { 
      "symbol": "<SYMBOL_FROM_PORTFOLIO>",
      "side": "long | short",
      "action": "hold | adjust_sl_tp | reduce_25 | reduce_50 | reduce_75 | close_position",
      "action_logic": {
        "zh": "【强制】必须首先结合 original_invalidation_rule 中的离场红线（包含中英文版本），判断当前最新数据是否已触发。如果触发，必须全仓平仓。然后再补充其他技术面/盈亏理由。",
        "en": "【MANDATORY】First, check the original_invalidation_rule (both ZH and EN) against current data. If triggered, you MUST close_position. Then add other technical/PnL reasoning."
      },
      "exit_plan": { "take_profit": 123.45, "stop_loss": 100.00 } /* Mandatory for adjust_sl_tp */
    }
  ],
  "new_opportunities": [
    {
      "symbol": "BTC",
      "action": "open_long | open_short | monitor",
      "leverage": 1, /* Dynamic leverage based on your risk tolerance */
      "position_size_usd": 0.0, /* Calculated based on your confidence and total_equity */
      "entry_reason": { 
        "zh": "【强制严格按此4点模板输出，无论是开仓还是monitor】：\n1) 为何是此币：[说明技术面支撑/阻力、RSI、均线偏离度及爆仓多空比等]\n2) 为何是现在：[说明当前价格动作与市场状态]\n3) 手动盈亏比(RRR)计算：[列出入场价、止损价风险%、止盈价盈利%，盈亏比=盈利%/风险%]\n4) 单笔风险占NAV比例：[列出计算过程，如风险$xx占NAV的0.xx% <= 2%]。如果是monitor，在此说明是因为盈亏比不足或其他原因。", 
        "en": "MUST STRICTLY FOLLOW THIS 4-POINT TEMPLATE (Even for monitor):\n1) Why this coin: [Technical/Sentiment summary]\n2) Why now: [Price action state]\n3) RRR Math: [Entry, SL risk%, TP profit%, RRR=X]\n4) NAV Risk: [Risk USD vs NAV%]. If monitor, explain math failure here." 
      },
      "exit_plan": {
        "take_profit": 120000,
        "stop_loss": 95000,
        "invalidation": {
          "zh": "明确描述：什么情况发生时，说明你的判断是错的，应该立即离场（例如：若价格收回X以上/以下，或鲸鱼流向反转，则多/空论点失效）",
          "en": "Clearly state: under what condition your thesis is WRONG and you must exit immediately (e.g., if price reclaims X, or whale flow reverses, the long/short thesis is invalidated)"
        }
      }
    }
  ]
}

*** LOGIC INTEGRITY RULES ***
1. **MAPPING FORCE**: Your `portfolio_management` list MUST contain exactly one entry for EVERY position listed in: {{MANDATORY_SYMBOLS_LIST}}. Every entry MUST have a non-generic reason.
2. **HEDGE AWARENESS**: If you hold both LONG and SHORT for the same coin, you MUST provide TWO entries in `portfolio_management`, specifying the correct `side` for each.
3. **NO GROUPING**: Provide an independent `action_logic` for EACH entry in `portfolio_management`.
4. **SCENARIO DISCIPLINE**: Your `hypothesis_scenario` must match your actions.
5. **DYNAMIC CAPITAL ALLOCATION**: You have FULL AUTONOMY to decide `position_size_usd` and `leverage` based on your confidence level against the provided `total_equity`. If you have high conviction, you may size up; if you are uncertain, size down or `monitor`.
6. **INVALIDATION REQUIRED**: Every `open_long` or `open_short` action MUST include a non-empty `invalidation`.

*** STYLE GUIDELINES ***
- **CLEAN TEXT**: Avoid redundant nested bolding like `** 【Header】 **`. Use simple brackets `[Header]` for section titles.
- **READABILITY**: Use clear spacing and avoid excessive Markdown symbols.
- **DIVERSIFIED FOCUS**: Do not focus only on ETH. Scan BTC, SOL, BNB, and DOGE data provided. If a non-ETH asset has a clearer setup, take it.
- **SWEAR JAR RULE (CRITICAL)**: Avoid absolute words like "Certain", "100%", "Definitely", "Impossible". Use probabilistic language (e.g., "Highly likely", "Potential risk", "70% probability").
- **NO CHATTER**: Do not include any text outside the JSON structure.
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
            
            # Fetch historical DB to map original invalidation rules
            try:
                from db_client import db
                history_db = db.get_data("agent_decisions", [])
            except Exception:
                history_db = []
                
            for p in positions:
                sym = p["symbol"]
                
                # Search backwards for the most recent open rule for this symbol
                invalidation_obj = {"zh": "离场红线未记录。请基于目前的 [技术指标详情] 和 [鲸鱼实况] 为资产重新定义离场信号。", "en": "No invalidation recorded. AS THE AI MANAGER, YOU MUST DEFINE NEW EXIT CONDITIONS based on current technicals/whale flow."}
                if isinstance(history_db, list):
                    for dec in history_db:
                        found = False
                        actions = dec.get("new_opportunities", []) + dec.get("actions", [])
                        for act in actions:
                            if act.get("symbol") == sym and "open_" in act.get("action", ""):
                                inv = act.get("exit_plan", {}).get("invalidation", {})
                                if isinstance(inv, dict):
                                    invalidation_obj = inv
                                else:
                                    invalidation_obj = {"zh": str(inv), "en": str(inv)}
                                found = True
                                break
                        if found:
                            break
                            
                try:
                    size = float(p.get("amount", 0))
                    val = size * p.get("currentPrice", 0) # Approx value
                except:
                    size = 0
                    val = 0
                    
                state["positions"].append({
                    "symbol": sym,
                    "side": p["type"],
                    "entry_price": p.get("entryPrice", 0),
                    "size": size,
                    "value_usd": val,
                    "pnl": p.get("pnl", 0),
                    "leverage": p.get("leverage", 1),
                    "pnlPercent": p.get("pnlPercent", 0),
                    "original_invalidation_rule": invalidation_obj
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
    """Reads the latest whale_analysis from MongoDB (Primary) or local JSON (Fallback)"""
    from db_client import db
    data = db.get_data("whale_analysis", default_value={})
    
    if not data:
        return "No Whale Data Available.", {}
    
    try:
            
        eth_stat_24h = data.get("eth", {}).get("stats_24h", {})
        eth_stat_7d = data.get("eth", {}).get("stats", {}) # stats is 7d
        
        sol_stat_24h = data.get("sol", {}).get("stats_24h", {})
        sol_stat_7d = data.get("sol", {}).get("stats", {})
        
        btc_stat = data.get("btc", {}).get("stats_24h", {})
        bnb_stat = data.get("bnb", {}).get("stats_24h", {})
        doge_stat = data.get("doge", {}).get("stats_24h", {})
        
        # Extract Liquidation Data (if available)
        eth_liq_long = eth_stat_24h.get("liquidation_long_usd")
        eth_liq_short = eth_stat_24h.get("liquidation_short_usd")
        sol_liq_long = sol_stat_24h.get("liquidation_long_usd")
        sol_liq_short = sol_stat_24h.get("liquidation_short_usd")
        btc_liq_long = btc_stat.get("liquidation_long_usd")
        btc_liq_short = btc_stat.get("liquidation_short_usd")
        bnb_liq_long = bnb_stat.get("liquidation_long_usd")
        bnb_liq_short = bnb_stat.get("liquidation_short_usd")
        doge_liq_long = doge_stat.get("liquidation_long_usd")
        doge_liq_short = doge_stat.get("liquidation_short_usd")
        
        eth_market = data.get("eth", {}).get("market", {})
        sol_market = data.get("sol", {}).get("market", {})
        btc_market = data.get("btc", {}).get("market", {})
        bnb_market = data.get("bnb", {}).get("market", {}) 
        doge_market = data.get("doge", {}).get("market", {})
        # Helper to format any value
        def f(val, fmt=".1f", default="N/A"):
            if val is None or val == "N/A": return default
            try:
                return format(float(val), fmt)
            except:
                return default

        # Helper to format tech
        def fmt_tech(m):
            if not m: return "No Tech Data"

            price_val = m.get('last_closed_close')
            sma50_val = m.get('sma_50')
            dist_sma50 = "N/A"
            if price_val is not None and sma50_val is not None and sma50_val > 0:
                dist_sma50 = f"{( (price_val - sma50_val) / sma50_val * 100):+.2f}%"

            # Formatting wicks separately as they need *100
            u_wick = m.get('upper_wick_ratio')
            l_wick = m.get('lower_wick_ratio')
            u_wick_str = f"{u_wick*100:.0f}%" if u_wick is not None else "N/A"
            l_wick_str = f"{l_wick*100:.0f}%" if l_wick is not None else "N/A"

            funding_val = m.get('funding_rate')
            funding_str = f"{funding_val*100:.4f}%" if funding_val is not None else "N/A"

            return (f"[4小时收盘价] ${f(price_val, '.2f')} | [均线乖离率] 4小时SMA50=${f(sma50_val, '.2f')} (偏离度:{dist_sma50}) | "
                    f"[RSI/ADX/MACD] RSI(14)={f(m.get('rsi_14'))} | ADX={f(m.get('adx_14'))} | MACD={f(m.get('macd_hist'), '.4f')} | "
                    f"[波动率 NATR] {f(m.get('natr_percent'), '.2f')}% | "
                    f"[上影线/下影线比率] 上影线(Upper)={u_wick_str} / 下影线(Lower)={l_wick_str} | "
                    f"[成交量与持仓(OI)] 成交量比率={f(m.get('vol_ratio_20'))}x | 24h OI变化={f(m.get('delta_oi_24h_percent'), '.2f')}% | "
                    f"[量化排名] {f(m.get('price_rank_20'), '.1f')}/100 | "
                    f"[资金费率] {funding_str} | [布林带] 宽度={f(m.get('bb_width'), '.3f')}, 趋势={m.get('bb_trend', 'N/A')}")

        # Token net flow: positive = tokens moving INTO exchange, negative = tokens moving OUT of exchange
        def fmt_token_flow(flow, symbol_name):
            if flow is None or flow == "N/A":
                return "N/A"
            try:
                flow_val = float(flow)
                if flow_val > 0:
                    return f"{flow_val:,.1f} {symbol_name} [提币囤货/FROM_EXCHANGE]"
                elif flow_val < 0:
                    return f"{flow_val:,.1f} {symbol_name} [充币抛售/TO_EXCHANGE]"
                else:
                    return f"0 {symbol_name}"
            except:
                return "N/A"

        # Stablecoin net flow: positive = stablecoins flowing IN, negative = flowing OUT
        def fmt_stable_flow(flow):
            if flow is None or flow == "N/A":
                return "N/A"
            try:
                flow_val = float(flow)
                if flow_val > 0:
                    return f"${flow_val:,.0f} [STABLECOIN IN]"
                elif flow_val < 0:
                    return f"${flow_val:,.0f} [STABLECOIN OUT]"
                else:
                    return f"$0"
            except:
                return "N/A"

        # Build Context String
        ctx = "=== 以太坊 (ETH) 鲸鱼数据分析 (对比 24h 与 7d 趋势) ===\n"
        eth_ls = eth_market.get("whale_ls_ratio")
        eth_pos = eth_market.get("whale_pos_ratio")
        eth_sent = eth_market.get("top_trader_sentiment")
        ctx += f"- [持仓L/S比] OKX大户账户数比={f(eth_ls, '.2f')} / 持仓量比={f(eth_pos, '.2f')}\n"
        ctx += f"- [交易所情绪] OKX 精英交易员情绪指数: {f(eth_sent, '.2f')}\n"
        eth_score_24h = eth_stat_24h.get('sentiment_score')
        eth_score_7d = eth_stat_7d.get('sentiment_score')
        ctx += f"- [鲸鱼评分] 综合情绪分: 24h={f(eth_score_24h, '.2f')} / 7d={f(eth_score_7d, '.2f')}\n"
        eth_tf_24h = eth_stat_24h.get('token_net_flow', 0)
        eth_tf_7d = eth_stat_7d.get('token_net_flow', 0)
        ctx += f"- [鲸鱼代币流向] 代币净流向: 24h={fmt_token_flow(eth_tf_24h, 'ETH')} / 7d={fmt_token_flow(eth_tf_7d, 'ETH')}\n"
        eth_sf_24h = eth_stat_24h.get('stablecoin_net_flow')
        eth_sf_7d = eth_stat_7d.get('stablecoin_net_flow')
        ctx += f"- [鲸鱼资金流向] 稳定币净流向: 24h={fmt_stable_flow(eth_sf_24h)} / 7d={fmt_stable_flow(eth_sf_7d)}\n"
        ctx += f"- [技术指标详情] {fmt_tech(eth_market)}\n"
        eth_liq_ratio = eth_liq_long / eth_liq_short if (eth_liq_long and eth_liq_short and eth_liq_short > 0) else 0
        ctx += f"- [24h爆仓量分布] 多单爆仓=${f(eth_liq_long, ',.0f')} / 空单爆仓=${f(eth_liq_short, ',.0f')} | 爆仓多空比={f(eth_liq_ratio, '.2f')}\n"
        
        ctx += "\n=== 索拉纳 (SOL) 鲸鱼数据分析 (对比 24h 与 7d 趋势) ===\n"
        sol_ls = sol_market.get("whale_ls_ratio")
        sol_pos = sol_market.get("whale_pos_ratio")
        sol_sent = sol_market.get("top_trader_sentiment")
        ctx += f"- [持仓L/S比] OKX大户账户数比={f(sol_ls, '.2f')} / 持仓量比={f(sol_pos, '.2f')}\n"
        ctx += f"- [交易所情绪] OKX 精英交易员情绪指数: {f(sol_sent, '.2f')}\n"
        sol_score_24h = sol_stat_24h.get('sentiment_score')
        sol_score_7d = sol_stat_7d.get('sentiment_score')
        ctx += f"- [鲸鱼评分] 综合情绪分: 24h={f(sol_score_24h, '.2f')} / 7d={f(sol_score_7d, '.2f')}\n"
        sol_tf_24h = sol_stat_24h.get('token_net_flow')
        sol_tf_7d = sol_stat_7d.get('token_net_flow')
        ctx += f"- [鲸鱼代币流向] 代币净流向: 24h={fmt_token_flow(sol_tf_24h, 'SOL')} / 7d={fmt_token_flow(sol_tf_7d, 'SOL')}\n"
        sol_sf_24h = sol_stat_24h.get('stablecoin_net_flow')
        sol_sf_7d = sol_stat_7d.get('stablecoin_net_flow')
        ctx += f"- [鲸鱼资金流向] 稳定币净流向: 24h={fmt_stable_flow(sol_sf_24h)} / 7d={fmt_stable_flow(sol_sf_7d)}\n"
        ctx += f"- [技术指标详情] {fmt_tech(sol_market)}\n"
        sol_liq_ratio = sol_liq_long / sol_liq_short if (sol_liq_long and sol_liq_short and sol_liq_short > 0) else 0
        ctx += f"- [24h爆仓量分布] 多单爆仓=${f(sol_liq_long, ',.0f')} / 空单爆仓=${f(sol_liq_short, ',.0f')} | 爆仓多空比={f(sol_liq_ratio, '.2f')}\n"
        # [BTC] Notes on data source
        ctx += "\n=== 比特币 (BTC) 交易所大户数据分析 ===\n"
        btc_ls = btc_market.get("whale_ls_ratio", 0)
        btc_pos = btc_market.get("whale_pos_ratio", 0)
        btc_sent = btc_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX大户账户数比={f(btc_ls, '.2f')} / 持仓量比={f(btc_pos, '.2f')}\n"
        ctx += f"- [交易所情绪] OKX 精英交易员情绪指数: {f(btc_sent, '.2f')}\n"
        ctx += f"- [提示] BTC 目前主要依赖交易所大户持仓与爆仓痛点分析，实时链上流向数据暂不适用 (显示为 N/A)。\n"
        ctx += f"- [鲸鱼评分] 综合情绪分: N/A\n"
        ctx += f"- [鲸鱼代币流向] 代币净流向: N/A\n"
        ctx += f"- [鲸鱼资金流向] 稳定币净流向: N/A\n"
        ctx += f"- [技术指标详情] {fmt_tech(btc_market)}\n"
        btc_liq_ratio = btc_liq_long / btc_liq_short if (btc_liq_long and btc_liq_short and btc_liq_short > 0) else 0
        ctx += f"- [24h爆仓量分布] 多单爆仓=${f(btc_liq_long, ',.0f')} / 空单爆仓=${f(btc_liq_short, ',.0f')} | 爆仓多空比={f(btc_liq_ratio, '.2f')}\n"
        ctx += f"注：BTC 目前仅支持交易所鲸鱼数据，不支持实时链上大额转账流向分析。\n"
        # [BNB] Notes on data source
        ctx += "\n=== 币安币 (BNB) 交易所大户数据分析 ===\n"
        bnb_ls = bnb_market.get("whale_ls_ratio", 0)
        bnb_pos = bnb_market.get("whale_pos_ratio", 0)
        bnb_sent = bnb_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX大户账户数比={f(bnb_ls, '.2f')} / 持仓量比={f(bnb_pos, '.2f')}\n"
        ctx += f"- [交易所情绪] OKX 精英交易员情绪指数: {f(bnb_sent, '.2f')}\n"
        ctx += f"- [提示] BNB 目前主要依赖交易所大户持仓分析，实时链上转账扫描暂未上线 (显示为 N/A)。\n"
        ctx += f"- [鲸鱼评分] 综合情绪分: N/A\n"
        ctx += f"- [鲸鱼代币流向] 代币净流向: N/A\n"
        ctx += f"- [鲸鱼资金流向] 稳定币净流向: N/A\n"
        ctx += f"- [技术指标详情] {fmt_tech(bnb_market)}\n"
        bnb_liq_ratio = bnb_liq_long / bnb_liq_short if (bnb_liq_long and bnb_liq_short and bnb_liq_short > 0) else 0
        ctx += f"- [24h爆仓量分布] 多单爆仓=${f(bnb_liq_long, ',.0f')} / 空单爆仓=${f(bnb_liq_short, ',.0f')} | 爆仓多空比={f(bnb_liq_ratio, '.2f')}\n"
        ctx += f"注：BNB 目前仅支持交易所鲸鱼数据，不支持 BSC 链上实时大额转账流向分析。\n"

        # [DOGE] Notes on data source
        ctx += "\n=== 狗狗币 (DOGE) 交易所大户数据分析 ===\n"
        doge_ls = doge_market.get("whale_ls_ratio", 0)
        doge_pos = doge_market.get("whale_pos_ratio", 0)
        doge_sent = doge_market.get("top_trader_sentiment", 0.5)
        ctx += f"- [持仓L/S比] OKX大户账户数比={f(doge_ls, '.2f')} / 持仓量比={f(doge_pos, '.2f')}\n"
        ctx += f"- [交易所情绪] OKX 精英交易员情绪指数: {f(doge_sent, '.2f')}\n"
        ctx += f"- [提示] DOGE 目前主要依赖交易所大户持仓分析，实时链上转账扫描暂未上线 (显示为 N/A)。\n"
        ctx += f"- [鲸鱼评分] 综合情绪分: N/A\n"
        ctx += f"- [鲸鱼代币流向] 代币净流向: N/A\n"
        ctx += f"- [鲸鱼资金流向] 稳定币净流向: N/A\n"
        ctx += f"- [技术指标详情] {fmt_tech(doge_market)}\n"
        doge_liq_ratio = doge_liq_long / doge_liq_short if (doge_liq_long and doge_liq_short and doge_liq_short > 0) else 0
        ctx += f"- [24h爆仓量分布] 多单爆仓=${f(doge_liq_long, ',.0f')} / 空单爆仓=${f(doge_liq_short, ',.0f')} | 爆仓多空比={f(doge_liq_ratio, '.2f')}\n"
        ctx += f"注：DOGE 目前仅支持交易所鲸鱼数据，不支持实时链上大额转账流向分析。\n"
        
        ctx += "\n*INSTRUCTION*: Compare 24h vs 7d Sentiment Scores and Token/Stablecoin flows for each asset and draw your own conclusions.*\n"
        
        # Add Macro Context (New Layer)
        macro = data.get("macro", {})
        fed = macro.get("fed_futures", {})
        japan = macro.get("japan_macro", {})
        liq = macro.get("liquidity_monitor", {})
        
        ctx += "\n=== 🌍 全球宏观背景 (GLOBAL MACRO CONTEXT) ===\n"
        fed_rate = (fed or {}).get('implied_rate')
        ctx += f"- 美联储基金利率 (Fed Rate): {f'{fed_rate}%' if fed_rate is not None else 'N/A'} (趋势: {(fed or {}).get('trend', 'N/A')})\n"
        if fed and 'change_5d_bps' in fed:
             ctx += f"  * 5日变动: {fed['change_5d_bps']} bps\n"
        
        jpy_price = (japan or {}).get('price')
        ctx += f"- 美元/日元 (USD/JPY): {jpy_price if jpy_price is not None else 'N/A'} (趋势: {(japan or {}).get('trend', 'N/A')})\n"
        if japan and 'change_5d_pct' in japan:
             ctx += f"  * 5日变动: {japan['change_5d_pct']}%\n"
             
        vix_price = (liq.get('vix') or {}).get('price')
        vix_trend = (liq.get('vix') or {}).get('trend', 'N/A')
        ctx += f"- VIX 恐慌指数: {vix_price if vix_price is not None else 'N/A'} (趋势: {vix_trend})\n"
        
        dxy_price = (liq.get('dxy') or {}).get('price')
        dxy_trend = (liq.get('dxy') or {}).get('trend', 'N/A')
        ctx += f"- 美元指数 (DXY): {dxy_price if dxy_price is not None else 'N/A'} (趋势: {dxy_trend})\n"
        
        # Add Daily Macro Trend (Derived from Brain's market data)
        # Brain's market_data.py now provides regime_1d, sma50_1d, sma200_1d
        daily_ctx = "=== 📈 1D 级别市场宏观趋势与环境 (1D MACRO) ===\n"
        for sym in ["BTC", "ETH", "SOL", "BNB", "DOGE"]:
            s_obj = data.get(sym.lower(), {})
            m_data = s_obj.get("market", {}) if "market" in s_obj else s_obj
            
            p = m_data.get("price", 0)
            rsi_1d = m_data.get("rsi_1d", 50.0)
            regime = m_data.get("regime_1d", "NEUTRAL")
            sma50 = m_data.get("sma50_1d", 0)
            sma200 = m_data.get("sma200_1d", 0)
            
            daily_ctx += f"- {sym}: 价格 ${p:,.2f} | 市场环境={regime} (RSI_1D={rsi_1d:.1f})\n"
            daily_ctx += f"  - 长期趋势: {'看涨 (BULLISH)' if p > sma50 else '看跌 (BEARISH)'} (对比 SMA50 ${sma50:.2f} / SMA200 ${sma200:.2f})\n"
            
            if sym == "BTC":
                # Inject Global Regime Marker for Risk Shield Logic
                daily_ctx += f"  - **全市场状态总结**: {regime} 市场\n"
            
        # Add News context from the same data obj
        news_root = data.get("news", {})
        news_items = news_root.get("items", {})
        news_str = "\n=== 📰 新闻焦点与市场情绪 (NEWS & SENTIMENT) ===\n"
        for source in ["macro", "bitcoin", "ethereum", "general"]:
            items = news_items.get(source, {}).get("items", [])
            for item in items[:2]:
                title = item.get('title_cn') or item.get('title')
                news_str += f"- [{source.upper()}] {title} ({item.get('published','N/A')})\n"

        # Final Combined String
        full_ctx = ctx + "\n" + daily_ctx + "\n" + news_str
        return full_ctx, data
    except Exception as e:
        return f"Error reading whale data: {e}", {}

def validate_and_enforce_decision(decision, whale_data_obj, whale_context, fear_index, executor):
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
    if "GLOBAL MARKET STATE: BULL" in whale_context:
        regime = "BULL"
    elif "GLOBAL MARKET STATE: BEAR" in whale_context:
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
    
    # Merge actions into a flat list
    raw_actions = []
    
    # --- 1.2 PORTFOLIO INTEGRITY CHECK (FILL MISSING) ---
    # Ensure every open position has a corresponding entry in portfolio_management
    try:
        open_positions = executor.get_all_positions()
        pm_list = decision.get("portfolio_management", [])
        if not isinstance(pm_list, list):
            pm_list = []
            decision["portfolio_management"] = pm_list
            
        for pos in open_positions:
            sym = pos["symbol"]
            side = pos.get("type", "net")
            
            # Robust match check: match by symbol AND side
            found_entry = None
            for entry in pm_list:
                pm_sym = entry.get("symbol", "")
                pm_side = entry.get("side", "")
                
                pm_sym_clean = pm_sym.split('(')[0].strip().upper()
                sym_clean = sym.upper()
                
                symbol_match = (pm_sym_clean == sym_clean or sym_clean.startswith(pm_sym_clean + "-") or pm_sym_clean in sym_clean)
                side_match = (pm_side.lower() == side.lower() or side == "net")
                
                if symbol_match and side_match:
                    found_entry = entry
                    break
            
            if not found_entry:
                print(f"🛡️ INTEGRITY: AI missed {sym} ({side}) in portfolio_management. Auto-filling 'hold'.")
                new_entry = {
                    "symbol": sym,
                    "side": side,
                    "action": "hold",
                    "action_logic": {
                        "zh": f"系统补丁：AI未返回该{side}持仓指令，默认维持当前状态以规避逻辑空缺风险。",
                        "en": f"System Patch: AI missed this {side} position in response. Auto-filling 'hold' to ensure constant monitoring."
                    }
                }
                pm_list.append(new_entry)
    except Exception as e:
        print(f"⚠️ Portfolio Integrity Check Failed: {e}")

    # A. Existing Portfolio
    pm_list = decision.get("portfolio_management", [])
    for entry in pm_list:
        raw_actions.append(entry)
        
    # B. New Opportunities
    raw_actions.extend(decision.get("new_opportunities", []))

    rejection_report = []
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
        # TRACKING: Adjust SL/TP
        if "adjust_sl" in act_type:
            validated_actions.append(action)
            continue
            
        # --- NEW Layer: Whale Dump Guard (Token vs Stable Flow) ---
        # Prevents "Inflow to Sell" traps
        sym_upper = symbol.upper()
        # Extract flows from context/data if available
        s_data = whale_data_obj.get(symbol.lower(), {}).get('stats_24h', {})
        t_flow = s_data.get('token_net_flow')
        st_flow = s_data.get('stablecoin_net_flow')
        
        # Guard against None values
        t_flow_val = float(t_flow) if t_flow is not None and t_flow != "N/A" else 0.0
        st_flow_val = float(st_flow) if st_flow is not None and st_flow != "N/A" else 0.0
        
        if act_type == "open_long" and t_flow_val > 0 and st_flow_val < 0:
             reason = f"🛡️ WHALE TRAP: {symbol} has Token INFLOW (${t_flow_val:.0f}) but Stablecoin OUTFLOW (${st_flow_val:.0f}). This is an 'Exchange Dump' setup, not accumulation. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue

        # --- NEW Layer: Liquidity Trap Guard (L/S Ratio) ---
        # Prevents chasing squeezes that are already over
        liq_long = s_data.get('liquidation_long_usd')
        liq_short = s_data.get('liquidation_short_usd')
        
        liq_long_val = float(liq_long) if liq_long is not None and liq_long != "N/A" else 0.0
        liq_short_val = float(liq_short) if liq_short is not None and liq_short != "N/A" else 0.0
        
        # Calculate ls_ratio safely
        ls_ratio = (liq_long_val / liq_short_val) if liq_short_val > 0 else 1.0

        if act_type == "open_long" and liq_short_val > 0 and liq_long_val >= 0:
            if ls_ratio < 0.1:
             reason = f"🛡️ LIQUIDITY TRAP: {symbol} L/S Ratio is too low ({ls_ratio:.2f}). Shorts already squeezed. No more fuel to go higher. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue
             
        if act_type == "open_short" and liq_short_val > 0 and ls_ratio > 10.0:
             reason = f"🛡️ REVERSAL TRAP: {symbol} L/S Ratio is too high ({ls_ratio:.2f}). Longs already flushed. Expect mean-reversion bounce. REJECTED."
             print(f"{reason}")
             action["action"] = "REJECTED"
             action["reason"] = reason
             validated_actions.append(action)
             continue

        # --- NEW Layer: Volatility & RRR Validation ---
        sym_key = symbol.lower()
        m_data = whale_data_obj.get(sym_key, {}).get('market', {})
        entry_price = m_data.get('price', 0)
        
        if entry_price > 0 and act_type.startswith("open_"):
            exit_plan = action.get("exit_plan", {})
            tp_input = exit_plan.get("take_profit")
            sl_input = exit_plan.get("stop_loss")
            
            # Parse Prices
            try:
                tp_px = float(str(tp_input).replace('$', '').replace(',', '')) if tp_input else 0
                sl_px = float(str(sl_input).replace('$', '').replace(',', '')) if sl_input else 0
            except:
                tp_px, sl_px = 0, 0
                
            if tp_px > 0 and sl_px > 0:
                dist_tp = abs(tp_px - entry_price)
                dist_sl = abs(entry_price - sl_px)
                rrr = dist_tp / dist_sl if dist_sl > 0 else 0
                
                # REJECTION RULE: RRR must be >= 1.5
                MIN_RRR = 1.45 # Giving a tiny buffer for rounding
                if rrr < MIN_RRR:
                    reason = f"🛡️ LOW RRR: {symbol} Risk/Reward Ratio is {rrr:.2f} (< {MIN_RRR}). Setup is biased towards 'Small Win / Big Loss'. REJECTED."
                    print(f"{reason}")
                    action["action"] = "REJECTED"
                    action["reason"] = reason
                    validated_actions.append(action)
                    continue

            # NAV Risk Cap (2% Max Risk) remains as a sizing rule
            if sl_px > 0:
                sl_dist_pct = abs(entry_price - sl_px) / entry_price * 100
                max_risk_usd = equity * 0.02
                current_risk_usd = (sl_dist_pct / 100) * size_usd
                
                if current_risk_usd > max_risk_usd and equity > 0:
                    refined_size_usd = max_risk_usd / (sl_dist_pct / 100)
                    print(f"🛡️ RISK: Downsizing {symbol} from ${size_usd:.0f} to ${refined_size_usd:.0f} (2% NAV Limit)")
                    action["position_size_usd"] = round(refined_size_usd, 2)
                    size_usd = refined_size_usd

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
        elif act_type.startswith("reduce_"):
             # Reduced exposure for existing position
             validated_actions.append(action)
        else:
            # For any other portfolio management actions that fell through (e.g. adjust_sl variants)
            # but ensure they are actually in validated_actions if they weren't caught by 'hold'/'close'/'adjust_sl'
            if action not in validated_actions:
                validated_actions.append(action)

    
    decision["actions"] = validated_actions
    decision["rejection_report"] = rejection_report
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
    # All necessary context is built into the final_prompt via whale_context
    # and other injections.
    
    # 2. Get Analysis Context (Consolidated from Brain)
    whale_context, whale_data_obj = get_whale_data()
    
    # Extract sub-contexts from whale_data_obj if needed, but get_whale_data already returns the string
    news_context = "" # News is now part of whale_context or injected separately
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_prompt = SYSTEM_PROMPT.replace("{{CURRENT_TIMESTAMP}}", current_time)
    
    # Precise Qlib Injection
    qlib_block = f"[[ QLIB ANALYSIS PAYLOAD ]]\n{qlib_payload_str}\n{qlib_stale_warning}"
    final_prompt = final_prompt.replace("{{QLIB_JSON_PAYLOAD}}", qlib_block)
    
    # Inject Consolidated Context
    final_prompt = final_prompt.replace("{{WHALE_CONTEXT}}", whale_context)
    
    # Portfolio State
    portfolio_state = get_portfolio_state(executor)
    final_prompt = final_prompt.replace("{{PORTFOLIO_STATE_JSON}}", portfolio_state)
    
    # DYNAMIC MAPPING FORCE
    p_state_obj = json.loads(portfolio_state)
    active_positions = [f"{p['symbol']} ({p['side']})" for p in p_state_obj.get("positions", [])]
    if not active_positions:
        mapping_list = "NONE (Portfolio is empty)"
    else:
        mapping_list = ", ".join(active_positions)
    final_prompt = final_prompt.replace("{{MANDATORY_SYMBOLS_LIST}}", mapping_list)
    
    # Clean up redundant tags (optional, but safer)
    final_prompt = final_prompt.replace("{{NEWS_CONTEXT}}", "Injected in Whale Context above.")
    final_prompt = final_prompt.replace("{{DAILY_CONTEXT}}", "Injected in Whale Context above.")

    # 2.5 Inject Dynamic Risk Limits
    # Determine Regime
    regime = "NEUTRAL"
    if "GLOBAL MARKET STATE: BULL" in whale_context: regime = "BULL"
    elif "GLOBAL MARKET STATE: BEAR" in whale_context: regime = "BEAR"

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
                    max_tokens=8192,
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
        decision = validate_and_enforce_decision(decision, whale_data_obj, whale_context, fear_index, executor)
        
        # --- UI ENRICHMENT: Ensure original rules are attached to actions for UI display ---
        if decision and "actions" in decision:
            for act in decision["actions"]:
                sym = act.get("symbol", "").upper()
                side = act.get("side", "").lower()
                # Check current portfolio to see if we have a rule for this
                for pos in p_state_obj.get("positions", []):
                    pos_sym = pos.get("symbol", "").upper()
                    pos_side = pos.get("side", "").lower()
                    if pos_sym == sym and (pos_side == side or side == ""):
                        if pos.get("original_invalidation_rule"):
                            act["original_invalidation_rule"] = pos["original_invalidation_rule"]
            
        print("\n💡 Dolores' Decision:")
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        
        # === NEW: EXECUTION LAYER ===
        # Re-fetch actions from decision (which now includes validated list)
        actions = decision.get("actions", [])
        
        for act in actions:
            symbol = act.get("symbol")
            action_type = act.get("action")
            
            # Logic Mapping for reason
            reason_obj = act.get("action_logic") or act.get("entry_reason") or {}
            
            # Initial reason extraction (will be prioritized later)
            reason_txt_en = reason_obj.get("en", "Maintaining position based on trend.")
            reason_txt_zh = reason_obj.get("zh", "根据当前趋势维持仓位。")
            
            # Fallback handling for close/reduce actions
            if "close" in action_type or "reduce" in action_type:
                # Check if we have an original invalidation rule to reference
                inv_rule = act.get("original_invalidation_rule", {})
                inv_zh = inv_rule.get("zh", "未定义") if isinstance(inv_rule, dict) else str(inv_rule)
                inv_en = inv_rule.get("en", "Not defined") if isinstance(inv_rule, dict) else str(inv_rule)

                if not reason_obj.get("en"):
                    reason_txt_en = f"Closing/Reducing position based on AI portfolio management rules (Ref Rule: {inv_en})."
                if not reason_obj.get("zh"):
                    reason_txt_zh = f"由于触发离场红线或AI风控逻辑（参考红线：{inv_zh}），对仓位进行平仓/减仓。"

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
                
                order_id = executor.execute_trade(symbol, action_type, amount, leverage, stop_loss=sl, take_profit=tp, natr_percent=coin_natr, pos_side=act.get("side"))

                # Only proceed to log memory and notify if an actual order was placed (or adjusted)
                # Note: okx_executor returns order_id string if successful, None if it skipped/failed
                if order_id:
                    # LOG TO MEMORY
                    try:
                        sym_lower = symbol.lower()
                        market_snapshot = whale_data_obj.get(sym_lower, {}).get('market', {})
                        entry_reason = act.get('entry_reason', {})
                        # Add reason string for text logs
                        reason_txt = entry_reason.get('en', reason_txt_en)
                        
                        memory.log_trade(symbol, action_type, amount, entry_reason, market_snapshot)
                        
                        # 🔔 SEND NOTIFICATION (Telegram/Discord)
                        # For reduce actions, position_size_usd is 0 (executor fetches real size dynamically)
                        if action_type.startswith("reduce_"):
                            pct = action_type.split("_")[-1]  # e.g. "25" from "reduce_25"
                            size_display = f"{pct}% of position"
                        elif "close" in action_type and amount == 0:
                            size_display = "ALL"
                        else:
                            size_display = f"${amount} ({leverage}x)"
                            
                        # Prioritize ZH reason for the user
                        # If we have a specific entry_reason from this loop iteration, use it
                        loop_reason_zh = entry_reason.get('zh', reason_txt_zh)
                        
                        notify_trade_execution(
                            symbol=symbol,
                            action=action_type,
                            size=size_display,
                            entry_price="MARKET",
                            sl=sl,
                            tp=tp,
                            reason=loop_reason_zh
                        )
                        
                    except Exception as log_err:
                        print(f"⚠️ Memory/Notify Log Error: {log_err}")
                else:
                    print(f"⚠️ Executor returned no order_id for {symbol} ({action_type}). Skipping notification.")
        
        # Save decision log
        try:
            from db_client import db
            # Use 'agent_decisions' (online collection) instead of local log
            history = db.get_data("agent_decisions", [])
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
        
        print(f"💾 Saving decision log to DB (agent_decisions)")
        try:
            from db_client import db
            db.save_data("agent_decisions", history)
            # Backup to local log just in case
            db.save_data("agent_decision_log", history)
            print("✅ Decision Log Saved Successfully!")
            
            # 🔔 SEND CYCLE SUMMARY & REJECTIONS
            try:
                # Rejection Alerts
                rej_list = decision.get("rejection_report", [])
                for rej in rej_list:
                    notify_rejection_alert(rej["symbol"], rej["reason"], rej["detail"])
                
                # Heartbeat Summary
                sentiment = decision.get("market_bias", {}).get("zh", "中立")
                conf = decision.get("confidence_probability", 70)
                
                # Calculate Heat
                heat_pct = (curr_long + curr_short) / equity * 100 if equity > 0 else 0
                
                # Append analysis summary
                regime = decision.get("context_analysis", {}).get("regime_safety", {}).get("zh", "")
                
                # Format monitor reasons
                monitor_msgs = []
                for act in actions:
                    sym = act.get("symbol", "")
                    action_type = act.get("action", "")
                    if action_type in ["monitor", "hold"]:
                        reason_obj = act.get("action_logic") or act.get("entry_reason") or {}
                        reason_txt_zh = reason_obj.get("zh", "Maintaining monitoring state.")
                        if reason_txt_zh:
                             # We escape just the text part, keep the <b> tags
                             safe_reason = escape_html(reason_txt_zh)
                             monitor_msgs.append(f"🔍 <b>{sym} ({action_type.upper()}):</b>\n{safe_reason}")
                             
                notify_cycle_summary(sentiment, conf, round(heat_pct, 1), regime, monitor_msgs, version=VERSION)
            except Exception as notify_err:
                print(f"⚠️ Notification Layer Error: {notify_err}")

        except Exception as e:
            print(f"❌ FAILED to save log to DB: {e}")
                
    except Exception as e:
        print(f"❌ Error calling DeepSeek (OpenAI SDK): {e}")

if __name__ == "__main__":
    run_agent()
