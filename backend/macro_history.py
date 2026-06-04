import json
import os
from statistics import pstdev
from datetime import datetime, timedelta, timezone


def _parse_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

class MacroHistory:
    def __init__(self, data_dir, db_client=None):
        self.filepath = os.path.join(data_dir, "macro_history.json")
        self.db = db_client
        self.history = self._load()
        if not self.history and self.db is not None:
            self.history = self._backfill_from_decision_cycles()
            if self.history:
                self.save()

    def _load(self):
        if self.db is not None and self.db.is_connected:
            try:
                data = self.db.get_list_strict("macro_history", sort_field="timestamp")
                if data:
                    return data
                # An empty live collection should be backfilled from persisted
                # decision cycles, not from potentially stale container files.
                return []
            except Exception as e:
                print(f"⚠️ Failed to load live macro history: {e}")

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

    def _backfill_from_decision_cycles(self):
        if self.db is None or not self.db.is_connected or self.db.db is None:
            return []
        try:
            pipeline = [
                {"$sort": {"generated_at": -1}},
                {"$limit": 500},
                {"$project": {
                    "_id": 0,
                    "generated_at": 1,
                    "facts": {"$arrayElemAt": ["$snapshots.macro_snapshot.event_facts", 0]},
                }},
            ]
            snapshots = []
            seen = set()
            for item in self.db.db["decision_cycles_v2"].aggregate(pipeline):
                facts = item.get("facts") or {}
                timestamp = item.get("generated_at")
                if not timestamp or timestamp in seen:
                    continue
                seen.add(timestamp)
                snapshots.append({
                    "timestamp": timestamp,
                    "fed_rate": facts.get("fed_implied_rate"),
                    "japan": facts.get("usdjpy_level"),
                    "dxy": facts.get("dxy_level"),
                    "vix": facts.get("vix_level"),
                    "us10y": facts.get("us10y_level"),
                    "global_stable_flow": facts.get("global_stable_flow"),
                    "global_stable_market_cap": facts.get("global_stable_market_cap"),
                    "fear_greed": facts.get("fear_greed_index"),
                })
            return sorted(snapshots, key=lambda row: str(row.get("timestamp") or ""))
        except Exception as e:
            print(f"⚠️ Failed to backfill macro history from decision cycles: {e}")
            return []

    def save(self):
        if self.db is not None:
            try:
                self.db.upsert_list_strict("macro_history", self.history)
            except Exception as e:
                print(f"⚠️ Failed to persist macro history to MongoDB: {e}")

        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to write local macro history backup: {e}")

    def add_snapshot(self, fed_data, japan_data, liquidity_data, stable_data=None, fear_greed_data=None):
        """
        Record a snapshot of current macro data.
        """
        stable_data = stable_data or {}
        fear_greed_data = fear_greed_data or {}
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "fed": fed_data.get("price"),
            "fed_rate": fed_data.get("implied_rate"),
            "japan": japan_data.get("price"),
            "dxy": liquidity_data.get("dxy", {}).get("price"),
            "vix": liquidity_data.get("vix", {}).get("price"),
            "us10y": liquidity_data.get("us10y", {}).get("price"),
            "global_stable_flow": stable_data.get("global_stable_flow"),
            "global_stable_market_cap": stable_data.get("global_stable_market_cap"),
            "fear_greed": fear_greed_data.get("value"),
        }
        self.history.append(snapshot)
        self._prune()
        self.save()

    def update_latest_snapshot(self, updates):
        """
        Patch the newest snapshot with late-arriving fields from the same run.
        """
        if not self.history or not isinstance(updates, dict):
            return
        self.history[-1].update(updates)
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
                    ts = _parse_timestamp(item["timestamp"])
                    if ts is None:
                        continue
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
                ts = _parse_timestamp(record["timestamp"])
                if ts is None:
                    continue
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
                ts = _parse_timestamp(record["timestamp"])
                if ts is None:
                    continue
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

    def get_recent_values(self, key, days=30):
        """
        Return numeric values within the recent window for simple dynamic thresholds.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        values = []
        for record in self.history:
            try:
                ts = _parse_timestamp(record["timestamp"])
                if ts is None:
                    continue
                if ts < cutoff:
                    continue
                value = record.get(key)
                if value is None:
                    continue
                values.append(float(value))
            except Exception:
                continue
        return values

    def get_std(self, key, days=30):
        """
        Return population standard deviation for the recent window.
        """
        values = self.get_recent_values(key, days=days)
        if len(values) < 2:
            return None
        try:
            return float(pstdev(values))
        except Exception:
            return None
