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
PAYLOAD_PATH = QLIB_DATA_DIR / "deepseek_payload.json"

# Initialize Qlib
if not BIN_DIR.exists():
    raise FileNotFoundError(f"Qlib BIN directory not found: {BIN_DIR}")
qlib.init(provider_uri=str(BIN_DIR), region="cn")

# -----------------------
# 2. Model Loading
# -----------------------

def load_model():
    if not MODEL_PATH.exists():
        print(f"❌ Model not found: {MODEL_PATH}")
        return None
    
    print(f"✅ Loading model: {MODEL_PATH}")
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    return model

# -----------------------
# 3. Inference Dataset
# -----------------------

def build_inference_dataset(latest_date: str):
    """
    Construct dataset with normalization for model inference.
    Must match training configuration exactly.
    """
    feature_cols = [
        "ret", "momentum_12",
        "macd_hist",
        "atr_14", "bb_width_20",
        "rsi_14",
        "rel_volume_20",
        "price_position_20",
        "funding_rate", "funding_rate_zscore",
        "oi_change", "oi_rsi",
    ]
    feature_exprs = [f"${col}" for col in feature_cols]

    # Fit range for RobustZScoreNorm (should match training or be a long recent window)
    fit_start = "2025-04-01"

    handler_config = {
        "class": "DataHandlerLP",
        "module_path": "qlib.data.dataset.handler",
        "kwargs": {
            "start_time": fit_start,
            "end_time": latest_date,
            "instruments": "all",
            "infer_processors": [
                {
                    "class": "RobustZScoreNorm",
                    "kwargs": {
                        "fields_group": "feature",
                        "clip_outlier": True,
                        "fit_start_time": fit_start,
                        "fit_end_time": latest_date,
                    },
                },
                {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
            ],
            "data_loader": {
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": feature_exprs,
                    },
                },
            },
        },
    }

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_config,
            "segments": {
                "test": (latest_date, latest_date),
            },
        },
    }

    dataset = init_instance_by_config(dataset_config)
    return dataset, feature_cols

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
    model = load_model()
    if model is None:
        return

    dataset, feature_cols = build_inference_dataset(latest_str)
    print("🔮 Predicting scores...")
    pred = model.predict(dataset)
    if isinstance(pred, pd.Series):
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
            "trained_until": "2025-11-21", # Approximate based on split
            "target": "next_24h_relative_return",
            "feature_count": len(feature_cols),
            "model_type": "LightGBM Ranker"
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

if __name__ == "__main__":
    if not HAS_QLIB:
        # Run fallback
        # Get latest date from CSV
        if CSV_PATH.exists():
            df = pd.read_csv(CSV_PATH)
            latest_date = pd.to_datetime(df['datetime']).max()
            simple_inference(latest_date)
        else:
            print("❌ Features file not found!")
            sys.exit(1)
        sys.exit(0)

    predict_and_export()
