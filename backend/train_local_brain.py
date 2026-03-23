
import qlib
import pandas as pd
from qlib.data import D
from qlib.utils import init_instance_by_config
from pathlib import Path
import pickle
import os
from qlib_config import QLIB_FEATURES, FEATURE_EXPRESSIONS, FIT_START_TIME

# 1. Init Qlib
BASE_DIR = Path(__file__).resolve().parent
BIN_DIR = BASE_DIR / "qlib_data" / "bin_multi_coin"
MODEL_OUT_PATH = BASE_DIR / "qlib_data" / "model_latest.pkl"

def train():
    if not BIN_DIR.exists():
        print(f"❌ Binary data not found at {BIN_DIR}")
        return

    qlib.init(provider_uri=str(BIN_DIR), region="cn")

    # 2. Config
    market = "all"
    feature_cols = QLIB_FEATURES
    feature_exprs = FEATURE_EXPRESSIONS
    label_expr = ["Ref($close, -6) / $close - 1"] # 24h return (6 * 4h)

    # Dates
    train_start = FIT_START_TIME 
    train_end = "2026-02-15"
    valid_start = "2026-02-16"
    valid_end = "2026-03-05"
    test_start = "2026-03-06"
    test_end = "2026-03-19"

    print(f"🚀 Training Model: {train_start} -> {train_end}...")

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
                        "feature": feature_exprs,
                        "label": label_expr,
                    },
                },
            },
        },
    }

    # 4. Dataset
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

    # 5. Model (LightGBM)
    model_config = {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
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

    print("✅ Retrain Complete!")

if __name__ == "__main__":
    train()
