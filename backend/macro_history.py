import json
import os
from datetime import datetime, timedelta

class MacroHistory:
    def __init__(self, data_dir):
        self.filepath = os.path.join(data_dir, "macro_history.json")
        self.history = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                    # Ensure it's a list
                    if isinstance(data, list):
                        return data
                    return []
            except Exception as e:
                print(f"⚠️ Failed to load macro history: {e}")
                return []
        return []

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save macro history: {e}")

    def add_snapshot(self, fed_data, japan_data, liquidity_data):
        """
        Record a snapshot of current macro data.
        """
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "fed": fed_data.get("price"),
            "fed_rate": fed_data.get("implied_rate"),
            "japan": japan_data.get("price"),
            "dxy": liquidity_data.get("dxy", {}).get("price"),
            "vix": liquidity_data.get("vix", {}).get("price"),
            "us10y": liquidity_data.get("us10y", {}).get("price")
        }
        self.history.append(snapshot)
        self._prune()
        self.save()

    def _prune(self, max_days=60, max_records=500):
        """
        Prune history to prevent unlimited growth.
        Criteria: Keep last 60 days OR max 500 records.
        """
        # 1. Length check
        if len(self.history) > max_records:
            self.history = self.history[-max_records:]
        
        # 2. Time check (optional, but good for cleanup)
        try:
            cutoff = datetime.utcnow() - timedelta(days=max_days)
            filtered = []
            for item in self.history:
                try:
                    ts = datetime.fromisoformat(item["timestamp"])
                    if ts > cutoff:
                        filtered.append(item)
                except:
                    pass 
            self.history = filtered
        except Exception as e:
            print(f"⚠️ Pruning failed: {e}")

    def get_change_percentage(self, key, current_val, days=5):
        """
        Calculate percentage change compared to 'days' ago.
        key: 'fed', 'japan', 'dxy', 'vix', 'us_10y'
        Returns: percentage float or None
        """
        if not self.history or current_val is None:
            return None

        # Find target timestamp
        target_time = datetime.utcnow() - timedelta(days=days)
        
        # Find closest record
        closest_record = None
        min_diff = timedelta(days=365)
        
        for record in self.history:
            try:
                ts = datetime.fromisoformat(record["timestamp"])
                diff = abs(ts - target_time)
                
                # Check if it's within reasonable window (e.g. +/- 2 days) to be valid comparison
                if diff < timedelta(days=2):
                     if diff < min_diff:
                         min_diff = diff
                         closest_record = record
            except:
                continue

        if closest_record and closest_record.get(key) is not None:
            prev_val = float(closest_record[key])
            if prev_val == 0: return 0.0
            return ((current_val - prev_val) / prev_val) * 100
        
        return None

    def get_change_absolute(self, key, current_val, days=5):
        """
        Calculate absolute change (e.g. for basis points or raw price).
        """
        pct = self.get_change_percentage(key, current_val, days) 
        # Wait, reuse logic finding record for DRY
        # But get_change_percentage returns %. Here we want abs diff.
        
        # Copied logic for safety logic:
        if not self.history or current_val is None:
            return None
            
        target_time = datetime.utcnow() - timedelta(days=days)
        closest_record = None
        min_diff = timedelta(days=365)
        
        for record in self.history:
            try:
                ts = datetime.fromisoformat(record["timestamp"])
                diff = abs(ts - target_time)
                if diff < timedelta(days=2):
                     if diff < min_diff:
                         min_diff = diff
                         closest_record = record
            except:
                continue
                
        if closest_record and closest_record.get(key) is not None:
             # Special case for FED RATE (implied_rate)
             if key == "fed_rate":
                  return (current_val - float(closest_record[key])) * 100 # bps
             return current_val - float(closest_record[key])
             
        return None
