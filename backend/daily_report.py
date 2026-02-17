import json
import os
from datetime import datetime
from notifier import send_telegram_message, send_discord_message

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "frontend", "data")

WHALE_PATH = os.path.join(DATA_DIR, "whale_analysis.json")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio_state.json")
DECISION_LOG_PATH = os.path.join(DATA_DIR, "agent_decision_log.json")

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def format_number(val, is_currency=True):
    if val is None: return "---"
    suffix = ""
    if abs(val) >= 1_000_000:
        val /= 1_000_000
        suffix = "M"
    elif abs(val) >= 1_000:
        val /= 1_000
        suffix = "k"
    
    fmt = f"{val:,.2f}{suffix}"
    return f"${fmt}" if is_currency else fmt

def generate_report():
    print("📊 Generating 4H Market Report...")
    
    # 1. Load Data
    whale_data = load_json(WHALE_PATH)
    portfolio = load_json(PORTFOLIO_PATH)
    decisions = load_json(DECISION_LOG_PATH)
    
    # Get latest decision
    latest_decision = decisions[0] if isinstance(decisions, list) and decisions else {}
    ai_summary = latest_decision.get("analysis_summary", {}).get("zh", "无最新分析")
    
    # 2. Portfolio Stats
    equity = portfolio.get("total_equity", 0)
    cash = portfolio.get("cash", 0)
    positions = portfolio.get("positions", [])
    pnl_24h = 0 # TODO: Calculate real 24h PnL from history if possible
    
    pos_str = ""
    if positions:
        for p in positions:
            pnl_pct = p.get("pnlPercent", 0) # Shadow prop? Or need calculation
            # Try to get live PnL if available or just list basic
            direction = "🟢 Long" if p["type"] == "long" else "🔴 Short"
            pos_str += f"• {direction} {p['symbol']} ({p['leverage']}x)\n"
    else:
        pos_str = "• 空仓 (Waiting for setup)"

    # 3. Market Stats (Top 3 Coins)
    market_str = ""
    coins = ["eth", "btc", "sol"]
    for coin in coins:
        data = whale_data.get(coin, {})
        stats = data.get("stats_24h", {})
        market = data.get("market", {})
        
        net_flow = stats.get("token_net_flow", 0)
        flow_icon = "fw" if net_flow > 0 else "bw" # Just text fallback
        flow_emoji = "🟢" if net_flow > 0 else "🔴"
        
        price = market.get("price", 0)
        change = market.get("change_24h", 0)
        
        market_str += f"**{coin.upper()}**: ${price:,.2f} ({change:+.2f}%)\n"
        market_str += f"   鲸鱼流向: {flow_emoji} {format_number(net_flow, False)} {coin.upper()}\n"

    # 4. Construct Message
    timestamp = datetime.now().strftime("%m-%d %H:%M")
    
    title = f"📢 **AI 市场快报 ({timestamp})**"
    
    body = f"""
{title}

🧠 **AI 观点**:
_{ai_summary[:100]}..._

💰 **当前持仓**:
**净值**: {format_number(equity)}
{pos_str}

🌊 **鲸鱼动向 (24h)**:
{market_str}

[查看详细仪表盘](http://localhost:5173/ai-copy-trading)
"""

    # 5. Send
    send_telegram_message(body)
    
    # Discord Embed
    embed = {
        "title": f"📊 4H Market Report ({timestamp})",
        "description": body.replace("**", "").replace("_", ""),
        "color": 3447003, # Blue
        "fields": [
            {"name": "Equity", "value": format_number(equity), "inline": True},
            {"name": "Positions", "value": str(len(positions)), "inline": True},
            {"name": "AI Sentiment", "value": ai_summary[:200]}
        ]
    }
    send_discord_message("", embed=embed)
    print("✅ Report sent.")

if __name__ == "__main__":
    generate_report()
