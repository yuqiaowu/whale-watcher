# Centrally manage features to keep Training and Inference in sync.
# Add new tech indicators here and both scripts will update automatically.

QLIB_FEATURES = [
    "ret", 
    "momentum_12", 
    "macd_hist", 
    "atr_14", 
    "bb_width_20", 
    "rsi_14", 
    "rel_volume_20", 
    "price_position_20", 
    "funding_rate", 
    "funding_rate_zscore", 
    "open_interest", 
    "oi_change", 
    "oi_rsi", 
    "btc_corr_24h", 
    "natr_14"
]

FEATURE_EXPRESSIONS = [f"${col}" for col in QLIB_FEATURES]

# Configuration for Dataset Handler
FIT_START_TIME = "2025-04-01"
# Training end dates usually move weekly
