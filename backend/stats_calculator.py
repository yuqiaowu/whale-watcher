import json
import os
from db_client import db

def calculate_stats():
    try:
        history = db.get_data("trade_history", [])
        if not history:
            return 0, 0
        
        # Filter for closed trades (those with a 'pnl' field)
        closed_trades = [t for t in history if "pnl" in t]
        
        total_trades = len(closed_trades)
        if total_trades == 0:
            return 0, 0
            
        winning_trades = [t for t in closed_trades if t.get("pnl", 0) > 0]
        win_rate = (len(winning_trades) / total_trades) * 100
        
        return total_trades, round(win_rate, 2)
    except Exception as e:
        print(f"Error calculating stats: {e}")
        return 0, 0
