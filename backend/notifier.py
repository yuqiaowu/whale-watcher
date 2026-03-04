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
    
if __name__ == "__main__":
    # Test
    notify_trade_execution("BTC", "OPEN_LONG", 0.5, 65000, 64000, 68000, "Test notification system.")
