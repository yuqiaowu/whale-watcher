"""
Export DeepSeek-ready JSON payload from Qlib multi-coin model.

Features:
- Loads trained Qlib model (qlib_data/model_latest.pkl)
- Predicts scores for the latest available 4H candle
- Fetches RAW feature values (not normalized) for better LLM interpretability
- Exports to qlib_data/deepseek_payload.json
"""

import json
import pickle
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List
import sys
from datetime import datetime
from qlib_config import QLIB_FEATURES, FEATURE_EXPRESSIONS, FIT_START_TIME
try:
    import qlib
    from qlib.data import D
    from qlib.config import REG_CN, REG_US
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.contrib.data.handler import Alpha158
    from qlib.utils import init_instance_by_config
    from qlib.workflow import R
    from qlib.workflow.record_temp import SignalRecord, PortAnaRecord
    HAS_QLIB = True
except ImportError:
    print("⚠️ Qlib not found. Using simple fallback for inference.")
    HAS_QLIB = False

# -----------------------
# Fallback Inference
# -----------------------

def simple_inference(date):
    """Fallback inference without Qlib"""
    print(f"⚠️ Running simple inference for {date}...")
    
    # Read features directly
    df = pd.read_csv(CSV_PATH)
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Filter for the specific date (or latest)
    # Note: date argument might be a string or datetime
    target_date = pd.to_datetime(date)
    
    # If target_date is not in df, use latest
    if target_date not in df['datetime'].values:
        latest_date = df['datetime'].max()
        print(f"  Target date {target_date} not found. Using latest: {latest_date}")
        target_date = latest_date
        
    latest_df = df[df['datetime'] == target_date].copy()
    
    market_map = {}
    for _, row in latest_df.iterrows():
        symbol = row['instrument']
        # Mock prediction (neutral)
        pred_score = 0.5 
        
        market_map[symbol] = {
            "price": row['close'],
            "volume": row['volume'],
            "return_4h": row.get('ret', 0),
            "volatility": row.get('volatility_20', 0),
            "rsi": row.get('rsi_14', 50),
            "macd": row.get('macd', 0),
            "model_score": pred_score,
            "model_signal": "HOLD" # Neutral
        }
        
    # Save payload
    with open(PAYLOAD_PATH, 'w') as f:
        json.dump(market_map, f, indent=4)
    
    print(f"✅ Saved fallback payload to {PAYLOAD_PATH}")

# -----------------------
# 1. Config & Init
# -----------------------

BASE_DIR = Path(__file__).resolve().parent
QLIB_DATA_DIR = BASE_DIR / "qlib_data"
BIN_DIR = QLIB_DATA_DIR / "bin_multi_coin"
CSV_PATH = QLIB_DATA_DIR / "multi_coin_features.csv"
MODEL_PATH = QLIB_DATA_DIR / "model_latest.pkl"
HANDLER_PATH = QLIB_DATA_DIR / "handler_latest.pkl"
PAYLOAD_PATH = QLIB_DATA_DIR / "deepseek_payload.json"

# Initialize Qlib (only if available)
if HAS_QLIB:
    if not BIN_DIR.exists():
        print(f"⚠️ Qlib BIN directory not found: {BIN_DIR}. Skipping init.")
        HAS_QLIB = False
    else:
        try:
            qlib.init(provider_uri=str(BIN_DIR), region="cn")
        except Exception as e:
            print(f"⚠️ qlib.init() failed: {e}. Falling back to CSV mode.")
            HAS_QLIB = False

# -----------------------
# 2. Model Loading
# -----------------------

def load_booster():
    model_txt = BASE_DIR / "qlib_data" / "model_latest.txt"
    model_pkl = BASE_DIR / "qlib_data" / "model_latest.pkl"
    
    import lightgbm as lgb
    
    # 1. Try Universal Text Model (Cross-Platform Safe)
    if model_txt.exists():
        print(f"✅ Loading Universal Text Model: {model_txt}")
        try:
            return lgb.Booster(model_file=str(model_txt))
        except Exception as e:
            print(f"⚠️ Failed to load .txt model: {e}")

    # 2. Fallback to Pickle (Mac-Only Safe usually)
    if model_pkl.exists():
        print(f"✅ Loading Pickle Model: {model_pkl}")
        try:
            with open(model_pkl, "rb") as f:
                qlib_model = pickle.load(f)
            return qlib_model.model
        except Exception as e:
            print(f"⚠️ Failed to load .pkl model: {e}")
            
    print("❌ No valid model found.")
    return None

# -----------------------
# 3. Inference Dataset
# -----------------------

def get_stateful_normalized_features(latest_date: str):
    """
    Manually loads raw data and sequences it through the pre-fitted (pickled) QLib processors.
    This GUARANTEES we use the exact mean/std learned on the developer's local machine!
    DatasetH recalculates them which causes drift due to UTC timezone offsets on Railway.
    """
    if not HANDLER_PATH.exists():
        print(f"❌ Handler not found: {HANDLER_PATH}")
        return None

    with open(HANDLER_PATH, "rb") as f:
        handler = pickle.load(f)

    # Allow fallback if exact calendar day mismatches
    from datetime import datetime, timedelta
    latest_dt = datetime.strptime(latest_date[:10], "%Y-%m-%d")
    latest_str_minus_1 = (latest_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        df = handler.data_loader.load(instruments="all", start_time=latest_date, end_time=latest_date)
    except Exception as e:
        df = pd.DataFrame()
        
    if df is None or df.empty:
        try:
            df = handler.data_loader.load(instruments="all", start_time=latest_str_minus_1, end_time=latest_date)
        except Exception:
            pass

    if df is None or df.empty:
        print(f"❌ Could not load raw feature dataframe for {latest_date} via Qlib DataLoader.")
        return None

    # Iterate over the natively fitted processors from training (skip DropnaLabel which is only for training)
    # This applies the exact frozen Z-Score parameters!
    for proc in handler.learn_processors:
        if "DropnaLabel" not in proc.__class__.__name__:
            df = proc(df)
        
    return df

# -----------------------
# 4. Main Logic
# -----------------------

def predict_and_export():
    # 1. Get latest timestamp
    cal = D.calendar(start_time="2025-01-01")
    if len(cal) == 0:
        print("❌ Calendar empty. Check Qlib data.")
        return
    latest_date = cal[-1]
    latest_str = str(latest_date)
    print(f"📅 Latest available data in Qlib Calendar: {latest_str}")
    
    # Debug: Check raw CSV latest date
    if CSV_PATH.exists():
        df_debug = pd.read_csv(CSV_PATH)
        df_debug['datetime'] = pd.to_datetime(df_debug['datetime'])
        print(f"🔍 CSV Latest Date: {df_debug['datetime'].max()}")
        print(f"   CSV Tail:\n{df_debug[['datetime', 'instrument', 'close']].tail(5)}")

    # 2. Load Model & Predict
    booster = load_booster()
    if booster is None:
        return

    print("🔮 Predicting scores using Stateful Handler...")
    processed_df = get_stateful_normalized_features(latest_str)
    if processed_df is None or processed_df.empty:
        print("⚠️ Processed inference dataframe is empty. Cannot predict.")
        return

    # Extract features matching QLib structure and predict natively with LightGBM Booster
    features = processed_df["feature"].values
    preds = booster.predict(features)
    
    pred = pd.Series(preds, index=processed_df.index, name="score")
    pred = pred.to_frame("score")
    
    # 3. Get RAW Features (for LLM context)
    # We read from the CSV directly to get un-normalized values
    print("📊 Fetching raw features...")
    raw_df = pd.read_csv(CSV_PATH)
    raw_df['datetime'] = pd.to_datetime(raw_df['datetime'])
    
    # Filter for latest date
    # Note: Qlib calendar might differ slightly in format, ensure alignment
    latest_ts = pd.Timestamp(latest_str)
    current_feats = raw_df[raw_df['datetime'] == latest_ts].copy()
    
    if current_feats.empty:
        print(f"⚠️ No raw data found for {latest_str} in CSV. Using previous close?")
        # Fallback: use last available row for each instrument
        current_feats = raw_df.sort_values('datetime').groupby('instrument').tail(1)
        print(f"   Using data from: {current_feats['datetime'].iloc[0]}")
    
    # Set index for join
    current_feats.set_index('instrument', inplace=True)
    
    # 4. Merge Scores with Raw Features
    # pred index is (datetime, instrument), reset to just instrument
    pred_reset = pred.reset_index()
    pred_reset.set_index('instrument', inplace=True)
    
    # Join
    result = pred_reset[['score']].join(current_feats, how='left')
    result = result.sort_values("score", ascending=False)

    # 5. Construct JSON Payload
    # Select columns that are useful for the Agent
    context_cols = [
        "close", "high", "low", "volume", # Basic
        "rsi_14", "macd_hist", "atr_14", "bb_width_20", # Technical
        "funding_rate", "funding_rate_zscore", # Sentiment
        "oi_change", "oi_rsi", # Sentiment
        "funding_rate", "funding_rate_zscore", # Sentiment
        "oi_change", "oi_rsi", # Sentiment
        "momentum_12", "ret",
        "btc_corr_24h", # Correlation
        "natr_14" # Normalized ATR
    ]
    
    # --- Suggestion C: Market Summary ---
    avg_momentum = result['momentum_12'].mean()
    avg_bb_width = result['bb_width_20'].mean()
    avg_funding = result['funding_rate'].mean()
    
    market_summary = {
        "trend": "bullish" if avg_momentum > 0.01 else "bearish" if avg_momentum < -0.01 else "neutral",
        "volatility": "high" if avg_bb_width > 0.15 else "low" if avg_bb_width < 0.05 else "medium",
        "leverage_sentiment": "bullish" if avg_funding > 0.0001 else "bearish" if avg_funding < 0 else "neutral",
        "metrics": {
            "avg_momentum_12": round(avg_momentum, 4),
            "avg_bb_width": round(avg_bb_width, 4),
            "avg_funding_rate": f"{avg_funding:.4%}"
        }
    }

    # --- Suggestion B: Baseline Recommendation ---
    # Logic: Take Top 3 coins with positive scores. Normalize weights.
    top_coins = result[result['score'] > 0].head(3)
    recommendations = []
    
    if not top_coins.empty:
        total_score = top_coins['score'].sum()
        for inst, row in top_coins.iterrows():
            weight = row['score'] / total_score
            recommendations.append({
                "symbol": str(inst),
                "weight": round(weight, 2),
                "score": round(row['score'], 4)
            })
    else:
        # Fallback if all scores are negative (Bear Market)
        # Recommend Shorting the weakest or holding cash
        recommendations.append({"symbol": "CASH", "weight": 1.0, "reason": "All scores negative"})

    payload = {
        "as_of": str(result['datetime'].iloc[0] if not result.empty and 'datetime' in result.columns else latest_str),
        "strategy": "Multi-Coin Relative Strength",
        
        # --- Suggestion A: Model Meta ---
        "model_meta": {
            "last_trained": datetime.fromtimestamp(MODEL_PATH.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            "target": "next_24h_relative_return",
            "feature_count": len(QLIB_FEATURES),
            "model_type": "LightGBM Ranker",
            "status": "up-to-date"
        },
        
        "market_summary": market_summary,
        "recommend_top": recommendations,
        
        "coins": []
    }

    for inst, row in result.iterrows():
        coin_data = {
            "symbol": str(inst),
            "qlib_score": round(float(row['score']), 4) if pd.notnull(row['score']) else 0,
            "rank": int(result.index.get_loc(inst)) + 1,
            "market_data": {}
        }
        
        for col in context_cols:
            if col in row:
                val = row[col]
                if pd.notnull(val):
                    # Format specific fields for readability
                    if "rate" in col or "ret" in col or "change" in col:
                        coin_data["market_data"][col] = f"{val:.4%}"
                    elif "rsi" in col:
                        coin_data["market_data"][col] = round(val, 2)
                    else:
                        coin_data["market_data"][col] = round(val, 4)
                else:
                    coin_data["market_data"][col] = None
        
        payload["coins"].append(coin_data)

    # 6. Save
    out_path = QLIB_DATA_DIR / "deepseek_payload.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Payload exported to: {out_path}")
    # Print preview
    print(json.dumps(payload, indent=2)) # Print full payload to show new sections

from market_data import get_strategy_metrics

def fetch_live_context_and_predict():
    """
    EXPERIMENTAL: Fetches real-time data from OKX and runs inference even if Qlib DB is stale.
    This ensures the 'as_of' date is actually today.
    """
    print("🌐 Fetching Live Market Context for Qlib Inference...")
    symbols = ["BTC", "ETH", "SOL", "BNB", "DOGE"]
    live_data = []
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load whale_analysis.json for funding Z-Score (not available from market_data)
    whale_zscore_map = {}
    whale_path = BASE_DIR.parent / "frontend" / "data" / "whale_analysis.json"
    try:
        with open(whale_path, "r") as f:
            whale_data = json.load(f)
        for sym in symbols:
            market = whale_data.get(sym.lower(), {}).get("market", {})
            whale_zscore_map[sym] = market.get("funding_zscore", 0)
    except Exception:
        pass  # Silently fall back to 0 if file not available
    
    for sym in symbols:
        metrics = get_strategy_metrics(sym)
        if metrics:
            # Prepare a row that matches the Alpha158/Inference expectation
            # We map the technical metrics to the feature names
            row = {
                "datetime": current_time,
                "instrument": sym,
                "close": metrics.get("price", 0),
                "volume": metrics.get("volume_24h", 0),
                "ret": metrics.get("change_24h", 0) / 100.0,
                "momentum_12": metrics.get("change_24h", 0) / 100.0,
                "macd_hist": metrics.get("macd_hist", 0),
                "atr_14": metrics.get("atr_14", 0),
                "bb_width_20": metrics.get("bb_width", 0),
                "rsi_14": metrics.get("rsi_14", 50),
                "vol_zscore_20": metrics.get("vol_zscore_20", 0),  # Z-Score for volume anomaly
                "rel_volume_20": metrics.get("vol_ratio_20", 1),
                "price_position_20": metrics.get("price_rank_20", 50) / 100.0,
                "funding_rate": metrics.get("funding_rate", 0),
                "funding_rate_zscore": metrics.get("funding_zscore", whale_zscore_map.get(sym, 0)),  # Z-Score: live OKX history first, whale_analysis fallback
                "oi_change": metrics.get("delta_oi_24h_percent", 0) / 100.0,
                "oi_rsi": metrics.get("oi_rsi", 50),
                "btc_corr_24h": metrics.get("btc_corr_24h", 1),
                "natr_14": metrics.get("natr_percent", 0)
            }
            live_data.append(row)
    
    if not live_data:
        print("❌ Failed to fetch any live data.")
        return None

    live_df = pd.DataFrame(live_data)
    
    # 2. Advanced Composite Scoring (Scientific Fallback)
    # Weights: Trend(40%), Explosion(30%), Contra-Sentiment(30%)
    payload = {
        "as_of": current_time,
        "strategy": "Live Proxy Ranking (Compound Formula)",
        "model_meta": {
            "type": "Heuristic Composite (Trend+Explosion+Sentiment)",
            "source": f"Live Market Data Snapshot @ {current_time}"
        },
        "market_summary": {
           "trend": "evaluating",
           "volatility": "evaluating"
        },
        "coins": []
    }
    
    scored_coins = []
    for idx, row in live_df.iterrows():
        symbol = row['instrument']
        
        # --- A. Trend Component (40%) ---
        # Normalize: ret (usually -0.05 to 0.05) and RSI (30-70)
        ret_score = np.clip(row['ret'] * 10, -1, 1) # 10% move = 1.0
        rsi_normalized = (row['rsi_14'] - 50) / 20.0 # 70 RSI = 1.0, 30 RSI = -1.0
        trend_score = (ret_score * 0.7 + rsi_normalized * 0.3)
        
        # --- B. Explosion Component (30%) ---
        # Volume Ratio (rel_volume_20): 1.0 is normal, 2.0+ is explosion
        vol_score = np.clip((row['rel_volume_20'] - 1.0) / 2.0, -1, 1)
        # OI Change (oi_change): Usually -0.02 to 0.02
        oi_score = np.clip(row['oi_change'] * 20, -1, 1) # 5% OI increase = 1.0
        explosion_score = (vol_score * 0.6 + oi_score * 0.4)
        
        # --- C. Contra-Sentiment / Squeeze Component (30%) ---
        # Funding Z-Score: > 2.0 is overbought crowd, < -2.0 is oversold crowd
        fz = row.get('funding_rate_zscore', 0)
        # Squeeze Logic: 
        # If price is down and funding is extremely negative -> Short Squeeze Potential (Bullish)
        # If price is up and funding is extremely positive -> Long liquidation risk (Bearish)
        sentiment_score = 0
        if row['ret'] < -0.01 and fz < -1.5:
            # Panic selling + short crowd = High score (reversal)
            sentiment_score = abs(fz) / 3.0 
        elif row['ret'] > 0.01 and fz > 1.5:
            # Over-leveraged longs + price peak = Penalty (safety)
            sentiment_score = -abs(fz) / 3.0
            
        # Composite Final Score
        final_score = (trend_score * 0.4) + (explosion_score * 0.3) + (sentiment_score * 0.3)
        
        # Append meta info for transparency
        scored_coins.append({
            "symbol": symbol,
            "qlib_score": round(final_score, 4),
            "trend_s": round(trend_score, 2),
            "explosion_s": round(explosion_score, 2),
            "sentiment_s": round(sentiment_score, 2),
            "market_data": {
                "price": row['close'],
                "rsi": round(row['rsi_14'], 2),
                "vol_ratio": round(row['rel_volume_20'], 2),
                "oi_change": f"{row['oi_change']:.2%}",
                "funding_z": round(fz, 2),
                "funding": f"{row['funding_rate']:.4%}"
            }
        })

    # Sort
    scored_coins = sorted(scored_coins, key=lambda x: x["qlib_score"], reverse=True)
    
    # Update Payload
    payload["coins"] = []
    for i, coin in enumerate(scored_coins):
        coin["rank"] = i + 1
        payload["coins"].append(coin)
    
    # Save
    with open(PAYLOAD_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Live Qlib Payload Exported: {current_time}")
    return payload

if __name__ == "__main__":
    # If Qlib is not available, go straight to Live Bridge
    if not HAS_QLIB:
        print("⚠️ Qlib not installed on this machine. Running Live Bridge directly...")
        fetch_live_context_and_predict()
    else:
        # Qlib is available — check if the calendar is fresh enough
        try:
            cal = D.calendar(start_time="2025-01-01")
            latest_qlib = cal[-1]
            
            # If Qlib is more than 3 days old, force live fetch
            if (datetime.now() - pd.to_datetime(latest_qlib)).days > 3:
                print(f"⚠️ Qlib Data is too old ({latest_qlib}). Switching to Live Bridge...")
                fetch_live_context_and_predict()
            else:
                predict_and_export()
        except Exception as e:
            print(f"⚠️ Qlib Calendar Check Error: {e}. Falling back to Live Bridge...")
            fetch_live_context_and_predict()
