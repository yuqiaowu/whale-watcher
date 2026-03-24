
import qlib
import pandas as pd
from qlib.data import D
from qlib.utils import init_instance_by_config
from pathlib import Path
import pickle
from datetime import datetime, timedelta
from qlib_config import QLIB_FEATURES, FEATURE_EXPRESSIONS, FIT_START_TIME

# 1. Init Qlib
BASE_DIR = Path(__file__).resolve().parent
BIN_DIR = BASE_DIR / "qlib_data" / "bin_multi_coin"
MODEL_OUT_PATH = BASE_DIR / "qlib_data" / "model_latest.pkl"
HANDLER_OUT_PATH = BASE_DIR / "qlib_data" / "handler_latest.pkl"

def train():
    if not BIN_DIR.exists():
        print(f"❌ Binary data not found at {BIN_DIR}")
        return

    qlib.init(provider_uri=str(BIN_DIR), region="cn")

    # 2. Config (Dynamic Rolling Window for 2026)
    market = "all"
    feature_cols = QLIB_FEATURES
    feature_expr_list = FEATURE_EXPRESSIONS
    label_expr = ["Ref($close, -6) / $close - 1"] # 24h return (6 * 4h)

    # Calculate rolling dates based on current time
    now_dt = datetime.now()
    # Expand training back to 2025-01-01 so LightGBM has 10,000+ rows to build actual splits
    # instead of a zero-split constant output.
    train_start = "2025-01-01"
    train_end = (now_dt - timedelta(days=5)).strftime("%Y-%m-%d")
    valid_start = (now_dt - timedelta(days=4)).strftime("%Y-%m-%d")
    valid_end = (now_dt - timedelta(days=2)).strftime("%Y-%m-%d")
    test_start = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    test_end = now_dt.strftime("%Y-%m-%d")

    print(f"🚀 Training: {train_start} -> {train_end}. Valid: {valid_start} -> {valid_end}. Test: {test_start} -> {test_end}")

    # 3. Data Handler
    handler_config = {
        "class": "DataHandlerLP",
        "module_path": "qlib.data.dataset.handler",
        "kwargs": {
            "start_time": train_start,
            "end_time": test_end,
            "instruments": market,
            "learn_processors": [
                {"class": "DropnaLabel"},
                {
                    "class": "RobustZScoreNorm", 
                    "kwargs": {
                        "fields_group": "feature", 
                        "clip_outlier": True,
                        "fit_start_time": train_start,
                        "fit_end_time": train_end
                    }
                },
                {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
            ],
            "data_loader": {
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": feature_expr_list,
                        "label": label_expr,
                    },
                },
            },
        },
    }

    # segments remain consistent with calculations above
    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_config,
            "segments": {
                "train": (train_start, train_end),
                "valid": (valid_start, valid_end),
                "test": (test_start, test_end),
            },
        },
    }

    # 5. Model (Relaxed Regularization to fix constant score bug)
    model_config = {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.85,
            "learning_rate": 0.05,
            "subsample": 0.85,
            "lambda_l1": 0.05, # Reduced from 205 to fix dead-score bug
            "lambda_l2": 0.05, # Reduced from 580 to fix dead-score bug
            "max_depth": 6,
            "num_leaves": 31,
            "num_threads": 2,
        },
    }

    # 6. Execute
    print("🔧 Initializing Dataset...")
    dataset = init_instance_by_config(dataset_config)
    print("🤖 Initializing Model...")
    model = init_instance_by_config(model_config)

    print("📈 Fitting Model...")
    model.fit(dataset)

    # 7. Save
    print(f"💾 Saving model to {MODEL_OUT_PATH}")
    with open(MODEL_OUT_PATH, "wb") as f:
        pickle.dump(model, f)

    print(f"💾 Saving handler to {HANDLER_OUT_PATH}")
    with open(HANDLER_OUT_PATH, "wb") as f:
        pickle.dump(dataset.handler, f)

    print("✅ Retrain Complete!")

if __name__ == "__main__":
    train()
