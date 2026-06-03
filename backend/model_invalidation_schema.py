ALLOWED_INVALIDATION_FIELDS = {
    "price",
    "macro_permission",
    "macro_mode",
    "p_up_8h",
    "p_down_8h",
    "p_flat_8h",
    "qlib_data_fresh",
    "relative_sma20_pct",
    "price_vs_vwap_4h_pct",
    "price_vs_vwap_16h_pct",
}

INVALIDATION_FIELD_ALIASES = {
    "current_price": "price",
}

LITERAL_INVALIDATION_VALUE_REFS = {
    "ALLOW_LONG",
    "ALLOW_SHORT",
    "ALLOW_BOTH",
    "RISK_ON",
    "RISK_OFF",
    "STRONG_RISK_OFF",
}

ALLOWED_INVALIDATION_REFERENCE_VALUES = {
    "model_stop_price",
    "recent_swing_high",
    "recent_swing_low",
    "sma50_4h",
    "sma200_1d",
    "structure_resistance_12bar_volume_confirmed",
    "structure_support_12bar_volume_confirmed",
    "structure_resistance_stop_short",
    "structure_support_stop_long",
}

ALLOWED_INVALIDATION_VALUE_REFS = ALLOWED_INVALIDATION_REFERENCE_VALUES | ALLOWED_INVALIDATION_FIELDS

ALLOWED_INVALIDATION_OPS = {">=", ">", "<=", "<", "==", "!="}


def normalize_invalidation_field(field: object) -> str:
    key = str(field or "").strip()
    return INVALIDATION_FIELD_ALIASES.get(key, key)


def normalize_invalidation_value_ref(value_ref: object) -> str:
    key = str(value_ref or "").strip()
    return INVALIDATION_FIELD_ALIASES.get(key, key)
