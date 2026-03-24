import os
import requests
import json
from datetime import datetime

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_telegram_message(message):
    """
    Sends a text message to Telegram.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not found.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=(5, 10))
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return False

def send_discord_message(message, embed=None):
    """
    Sends a message to Discord via Webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Discord webhook not found.")
        return False

    payload = {"content": message}
    if embed:
        payload["embeds"] = [embed]
        
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=(5, 10))
        return resp.status_code in [200, 204]
    except Exception as e:
        print(f"❌ Discord send failed: {e}")
        return False

def notify_trade_execution(symbol, action, size, entry_price, sl=None, tp=None, reason="AI Decision"):
    """
    Constructs a rich trade alert and sends it to all configured channels.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if action.lower() == "adjust_sl":
        side_icon = "🛡️"
        action_text = "RISK ADJUSTED"
        color_code = 3447003 # Blue
    else:
        side_icon = "🟢" if "long" in action.lower() or "buy" in action.lower() else "🔴"
        action_text = "TRADE EXECUTED"
        color_code = 5763719 if "long" in action.lower() else 15548997
    
    # --- Format Message ---
    title = f"{side_icon} {action_text}: {action.upper()} {symbol}"
    
    body = f"""
**Symbol:** `{symbol}`
**Action:** `{action.upper()}`
**Size:** `{size}`
**Entry Price:** `${entry_price}`
**Time:** `{timestamp}`

🛡️ **Risk Management:**
• **Stop Loss:** `{sl if sl else '---'}`
• **Take Profit:** `{tp if tp else '---'}`

🧠 **Rationale:**
_{reason}_
"""
    
    print(f"📢 Sending Trade Alert for {symbol}...")
    
    # 1. Telegram
    tg_msg = f"<b>{title}</b>\n" + f"""
<b>Symbol:</b> <code>{symbol}</code>
<b>Action:</b> <code>{action.upper()}</code>
<b>Size:</b> <code>{size}</code>
<b>Entry Price:</b> <code>${entry_price}</code>
<b>Time:</b> <code>{timestamp}</code>

🛡️ <b>Risk Management:</b>
• <b>Stop Loss:</b> <code>{sl if sl else '---'}</code>
• <b>Take Profit:</b> <code>{tp if tp else '---'}</code>

🧠 <b>Rationale:</b>
<i>{reason}</i>
"""
    send_telegram_message(tg_msg)
    
    # 2. Discord (Rich Embed)
    discord_embed = {
        "title": title,
        "description": body.replace("*", "").replace("_", ""), # Clean markdown slightly for Discord description
        "color": color_code,
        "footer": {"text": "Dolores AI Agent"}
    }
    send_discord_message("", embed=discord_embed)
    
def notify_rejection_alert(symbol, reason, detail=""):
    """
    Warns the user when the Risk Shield blocks an AI suggested trade.
    """
    title = f"🛡️ RISK SHIELD: BLOCKED {symbol}"
    msg = f"<b>{title}</b>\n\n<b>Reason:</b> <code>{reason}</code>\n<b>Detail:</b> <i>{detail}</i>\n\n<i>Dolores was prevented from entering this trade to preserve NAV safety.</i>"
    send_telegram_message(msg)
    send_discord_message(f"🛡️ **RISK SHIELD:** Blocked `{symbol}`. Reason: `{reason}`. {detail}")

def notify_cycle_summary(sentiment, confidence, portfolio_heat, regime="", monitor_msgs=None):
    """
    Sends a periodic heartbeat status summary, including analysis and monitor logics.
    """
    if monitor_msgs is None:
        monitor_msgs = []
        
    title = "💓 CYCLE SUMMARY: Dolores is Alive"
    msg = f"<b>{title}</b>\n\n<b>Market Sentiment:</b> <code>{sentiment}</code>\n<b>AI Confidence:</b> <code>{confidence}%</code>\n<b>Portfolio Heat:</b> <code>{portfolio_heat}% NAV</code>\n"
    
    if regime:
        msg += f"\n<b>大盘安全判定 (Regime):</b>\n<i>{regime}</i>\n"
        
    if monitor_msgs:
        msg += f"\n<b>最新标的观望分析 (Monitor Logics):</b>\n"
        for m in monitor_msgs:
            msg += f"{m}\n\n"
            
    msg += f"\n<i>Analysis cycle complete. No immediate critical executions triggered.</i>"
    
    send_telegram_message(msg)
    send_discord_message(f"💓 **CYCLE SUMMARY:** {sentiment} | Conf: {confidence}% | Heat: {portfolio_heat}% NAV")
    
if __name__ == "__main__":
    # Test
    notify_trade_execution("BTC", "OPEN_LONG", 0.5, 65000, 64000, 68000, "Test notification system.")
