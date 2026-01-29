import os
import json
import requests
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def format_currency(value):
    """Format value as USD currency string (e.g., $1.2M, $500k)."""
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif abs(value) >= 1_000:
        return f"${value/1_000:.1f}k"
    else:
        return f"${value:.2f}"

def send_daily_report(data_path="frontend/data/whale_analysis.json"):
    """
    Reads the latest analysis data and sends a formatted report to Telegram.
    """
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram Bot Token or Chat ID missing. Skipping notification.")
        return

    try:
        # Load Data
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, data_path)
        
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Prepare Message Content
        # AI Summary (Chinese preferred)
        ai_summary_obj = data.get("ai_summary", {})
        # Handle both string and object formats for robustness
        ai_text = ""
        if isinstance(ai_summary_obj, str):
             ai_text = ai_summary_obj
        else:
             # Helper to flatten dict to string
             def flatten_dict(d, indent=0):
                 lines = []
                 for k, v in d.items():
                     prefix = "  " * indent
                     if isinstance(v, dict):
                         lines.append(f"{prefix}**{k}**:")
                         lines.append(flatten_dict(v, indent + 1))
                     else:
                         lines.append(f"{prefix}- {k}: {v}")
                 return "\n".join(lines)

             # robustly get zh or en
             if "zh" in ai_summary_obj:
                 val = ai_summary_obj["zh"]
             elif "en" in ai_summary_obj:
                 val = ai_summary_obj["en"]
             else:
                 # No zh/en keys, treat the whole object as the content
                 val = ai_summary_obj

             if isinstance(val, dict):
                 # It's a dict (nested structure), flatten it
                 ai_text = flatten_dict(val)
             elif val:
                 ai_text = str(val)
             else:
                 ai_text = "No summary."

        # Clean AI text using regex for safe HTML replacement
        import re
        # Replace **text** with <b>text</b>
        ai_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', ai_text)
        # Replace * text with • text (bullet points)
        ai_text = re.sub(r'^\s*\*\s+', '• ', ai_text, flags=re.MULTILINE)
        
        # Stats Extraction
        eth_stats_7d = data["eth"]["stats"]
        eth_stats_24h = data["eth"]["stats_24h"]
        sol_stats_7d = data["sol"]["stats"]
        sol_stats_24h = data["sol"]["stats_24h"]
        
        updated_at = data.get("updated_at", "").split("T")[0]

        # Construct Message
        message = f"""
🐋 <b>Whale Watcher Daily Report</b> 📅 {updated_at}

🤖 <b>AI Market Insight:</b>
{ai_text}

➖➖➖➖➖➖➖➖➖➖➖

🔷 <b>ETH Chain (Smart Money)</b>
<b>24h Flow:</b>
• Net Token: {format_currency(eth_stats_24h.get('token_net_flow', 0))}
• Net Stable: {format_currency(eth_stats_24h.get('stablecoin_net_flow', 0))}
• Sentiment: {eth_stats_24h.get('sentiment_score', 0):.2f}

<b>7d Trend:</b>
• Net Token: {format_currency(eth_stats_7d.get('token_net_flow', 0))}
• Net Stable: {format_currency(eth_stats_7d.get('stablecoin_net_flow', 0))}
• Sentiment: {eth_stats_7d.get('sentiment_score', 0):.2f}

➖➖➖➖➖➖➖➖➖➖➖

🟣 <b>SOL Chain (Speculative)</b>
<b>24h Flow:</b>
• Net Token: {format_currency(sol_stats_24h.get('token_net_flow', 0))}
• Net Stable: {format_currency(sol_stats_24h.get('stablecoin_net_flow', 0))}
• Sentiment: {sol_stats_24h.get('sentiment_score', 0):.2f}

<b>7d Trend:</b>
• Net Token: {format_currency(sol_stats_7d.get('token_net_flow', 0))}
• Net Stable: {format_currency(sol_stats_7d.get('stablecoin_net_flow', 0))}
• Sentiment: {sol_stats_7d.get('sentiment_score', 0):.2f}

➖➖➖➖➖➖➖➖➖➖➖
<i>Fear & Greed Index: {data.get("fear_greed", {}).get("value", "N/A")}</i>
"""

        # Send Request
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        print("Sending Telegram notification...")
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            print("Telegram notification sent successfully!")
        else:
            print(f"Failed to send Telegram notification: {response.text}")

    except Exception as e:
        print(f"Error in send_daily_report: {e}")

if __name__ == "__main__":
    send_daily_report()
