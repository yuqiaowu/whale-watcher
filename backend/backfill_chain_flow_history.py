import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "qlib_data" / "multi_coin_features.csv"
CHAIN_FLOW_CACHE = BASE_DIR / "qlib_data" / "chain_flow_4h.csv"
ETH_FLOW_TOKENS = {"WETH", "USDT", "USDC"}
SOL_FLOW_TOKENS = {"SOL", "USDC"}
ETH_BACKFILL_MIN_USD = 5_000
SOL_BACKFILL_MIN_USD = 1_000

env_path = BASE_DIR.parent / ".env"
load_dotenv(dotenv_path=env_path)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
ALCHEMY_SOLANA_API_KEY = os.getenv("ALCHEMY_SOLANA_API_KEY")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY_2") or os.getenv("MORALIS_API_KEY")


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1]
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in ts else "%Y-%m-%dT%H:%M:%S"
    return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)


def bar_floor_4h(dt: datetime) -> datetime:
    return dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def classify_flow(signal: str, symbol: str, amount_usd: float) -> tuple[float, float]:
    token_flow = 0.0
    stable_flow = 0.0
    if symbol in {"USDT", "USDC"}:
        if signal == "BULLISH_INFLOW":
            stable_flow += amount_usd
        elif signal == "BEARISH_OUTFLOW":
            stable_flow -= amount_usd
    else:
        if signal == "BEARISH_INFLOW":
            token_flow -= amount_usd
        elif signal == "BULLISH_OUTFLOW":
            token_flow += amount_usd
    return token_flow, stable_flow


def _load_crypto_brain_dependencies():
    try:
        from backend.crypto_brain import (
            TOKENS,
            TOKEN_DECIMALS,
            SOLANA_TOKENS,
            MIN_VALUE_USD,
            MIN_VALUE_USD_SOL,
            EXCHANGES,
            get_token_price,
            get_solana_price,
        )
    except ModuleNotFoundError:
        from crypto_brain import (
            TOKENS,
            TOKEN_DECIMALS,
            SOLANA_TOKENS,
            MIN_VALUE_USD,
            MIN_VALUE_USD_SOL,
            EXCHANGES,
            get_token_price,
            get_solana_price,
        )
    return {
        "TOKENS": TOKENS,
        "TOKEN_DECIMALS": TOKEN_DECIMALS,
        "SOLANA_TOKENS": SOLANA_TOKENS,
        "MIN_VALUE_USD": MIN_VALUE_USD,
        "MIN_VALUE_USD_SOL": MIN_VALUE_USD_SOL,
        "ETH_EXCHANGES": {k.lower(): v for k, v in EXCHANGES.items()},
        "get_token_price": get_token_price,
        "get_solana_price": get_solana_price,
    }


def _get_solana_history_key() -> tuple[str | None, str]:
    if ALCHEMY_SOLANA_API_KEY:
        return ALCHEMY_SOLANA_API_KEY, "alchemy"
    if HELIUS_API_KEY:
        return HELIUS_API_KEY, "helius"
    return None, "none"


def _ensure_csv_schema():
    try:
        from backend.update_qlib_data import ensure_csv_schema
    except ModuleNotFoundError:
        from update_qlib_data import ensure_csv_schema
    ensure_csv_schema()


def fetch_eth_historical_transfers(
    start_dt: datetime,
    end_dt: datetime,
    max_pages_per_token: int = 5,
    exchange_limit: int | None = None,
) -> list[dict]:
    if not ETHERSCAN_API_KEY:
        raise RuntimeError("ETHERSCAN_API_KEY missing")
    deps = _load_crypto_brain_dependencies()

    etherscan_url = "https://api.etherscan.io/v2/api"
    all_transfers: list[dict] = []

    dedup = set()
    exchange_addresses = list(deps["ETH_EXCHANGES"].keys())
    if exchange_limit:
        exchange_addresses = exchange_addresses[:exchange_limit]

    for symbol, address in deps["TOKENS"].items():
        if symbol not in ETH_FLOW_TOKENS:
            continue
        price = deps["get_token_price"](address)
        if not price:
            continue
        print(f"[ETH] scanning {symbol}", flush=True)
        for exchange_addr in exchange_addresses:
            oldest_seen = end_dt
            for page in range(1, max_pages_per_token + 1):
                params = {
                    "chainid": "1",
                    "module": "account",
                    "action": "tokentx",
                    "address": exchange_addr,
                    "contractaddress": address,
                    "page": page,
                    "offset": 200,
                    "sort": "desc",
                    "apikey": ETHERSCAN_API_KEY,
                }
                resp = requests.get(etherscan_url, params=params, timeout=(6, 20))
                data = resp.json()
                rows = data.get("result") if isinstance(data, dict) else None
                if not isinstance(rows, list) or not rows:
                    break

                stop_paging = False
                for tx in rows:
                    try:
                        ts_epoch = int(tx["timeStamp"])
                        tx_dt = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                        oldest_seen = min(oldest_seen, tx_dt)
                        if tx_dt < start_dt:
                            stop_paging = True
                            continue
                        if tx_dt > end_dt:
                            continue

                        dedup_key = (tx["hash"], tx.get("logIndex", ""), symbol)
                        if dedup_key in dedup:
                            continue
                        dedup.add(dedup_key)

                        decimals = int(tx.get("tokenDecimal", deps["TOKEN_DECIMALS"].get(symbol, 18)))
                        amount = float(tx["value"]) / (10 ** decimals)
                        amount_usd = amount * price
                        if amount_usd < ETH_BACKFILL_MIN_USD:
                            continue

                        from_addr = tx["from"].lower()
                        to_addr = tx["to"].lower()
                        is_exchange_in = to_addr in deps["ETH_EXCHANGES"]
                        is_exchange_out = from_addr in deps["ETH_EXCHANGES"]

                        signal = "NEUTRAL"
                        if symbol in {"USDT", "USDC"}:
                            if is_exchange_in:
                                signal = "BULLISH_INFLOW"
                            elif is_exchange_out:
                                signal = "BEARISH_OUTFLOW"
                        else:
                            if is_exchange_in:
                                signal = "BEARISH_INFLOW"
                            elif is_exchange_out:
                                signal = "BULLISH_OUTFLOW"

                        if signal == "NEUTRAL":
                            continue

                        all_transfers.append(
                            {
                                "hash": tx["hash"],
                                "timestamp": iso_utc(tx_dt),
                                "instrument": "ETH",
                                "symbol": symbol,
                                "amount_usd": amount_usd,
                                "signal": signal,
                            }
                        )
                    except Exception:
                        continue

                if stop_paging or oldest_seen < start_dt:
                    break
                time.sleep(0.12)

    return all_transfers


def fetch_sol_historical_swaps(start_dt: datetime, end_dt: datetime, max_pages_per_token: int = 10) -> list[dict]:
    if not MORALIS_API_KEY:
        raise RuntimeError("MORALIS_API_KEY missing")
    deps = _load_crypto_brain_dependencies()

    headers = {"X-API-Key": MORALIS_API_KEY}
    prices = {symbol: deps["get_solana_price"](address) for symbol, address in deps["SOLANA_TOKENS"].items()}
    all_swaps: list[dict] = []

    for symbol, address in deps["SOLANA_TOKENS"].items():
        if symbol not in SOL_FLOW_TOKENS:
            continue
        print(f"[SOL] scanning {symbol}", flush=True)
        url = f"https://solana-gateway.moralis.io/token/mainnet/{address}/swaps"
        params = {"limit": 100}
        pages = 0

        while pages < max_pages_per_token:
            resp = requests.get(url, headers=headers, params=params, timeout=(10, 30))
            data = resp.json()
            rows = data.get("result", [])
            if not rows:
                break

            stop_paging = False
            for swap in rows:
                try:
                    tx_dt = parse_iso(swap["blockTimestamp"])
                    if tx_dt < start_dt:
                        stop_paging = True
                        continue
                    if tx_dt > end_dt:
                        continue

                    bought_addr = swap["bought"]["address"]
                    sold_addr = swap["sold"]["address"]
                    raw_amount = 0.0
                    signal = "NEUTRAL"

                    if bought_addr == address:
                        raw_amount = float(swap["bought"]["amount"])
                        signal = "BULLISH_OUTFLOW"
                        if symbol in {"USDC", "USDT"}:
                            signal = "BEARISH_OUTFLOW"
                    elif sold_addr == address:
                        raw_amount = float(swap["sold"]["amount"])
                        signal = "BEARISH_INFLOW"
                        if symbol in {"USDC", "USDT"}:
                            signal = "BULLISH_INFLOW"
                    else:
                        continue

                    amount_usd = raw_amount * float(prices.get(symbol, 0.0) or 0.0)
                    if amount_usd == 0:
                        amount_usd = float(swap.get("totalValueUsd", 0.0) or 0.0)
                    if amount_usd < SOL_BACKFILL_MIN_USD:
                        continue
                    if signal == "NEUTRAL":
                        continue

                    all_swaps.append(
                        {
                            "hash": swap["transactionHash"],
                            "timestamp": swap["blockTimestamp"],
                            "instrument": "SOL",
                            "symbol": symbol,
                            "amount_usd": amount_usd,
                            "signal": signal,
                        }
                    )
                except Exception:
                    continue

            pages += 1
            cursor = data.get("cursor")
            if stop_paging or not cursor:
                break
            params["cursor"] = cursor
            time.sleep(0.2)

    return all_swaps


def fetch_sol_historical_transfers_helius(start_dt: datetime, end_dt: datetime, max_pages: int = 20) -> list[dict]:
    key, provider = _get_solana_history_key()
    if provider != "helius" or not key:
        return []

    endpoint = "https://api.helius.xyz/v0/addresses/{address}/transactions"
    watched = {
        "SOL": "So11111111111111111111111111111111111111112",
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    }
    prices = {symbol: _load_crypto_brain_dependencies()["get_solana_price"](mint) for symbol, mint in watched.items()}
    all_events: list[dict] = []

    for symbol, mint in watched.items():
        print(f"[SOL][helius] scanning {symbol}", flush=True)
        before = None
        for _ in range(max_pages):
            params = {"api-key": key, "limit": 100}
            if before:
                params["before"] = before
            resp = requests.get(endpoint.format(address=mint), params=params, timeout=30)
            if resp.status_code != 200:
                break
            rows = resp.json()
            if not isinstance(rows, list) or not rows:
                break

            stop_paging = False
            for tx in rows:
                ts = tx.get("timestamp")
                if not ts:
                    continue
                tx_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if tx_dt < start_dt:
                    stop_paging = True
                    continue
                if tx_dt > end_dt:
                    continue

                for transfer in tx.get("tokenTransfers", []) or []:
                    mint_addr = transfer.get("mint")
                    if mint_addr != mint:
                        continue
                    amount = float(transfer.get("tokenAmount") or 0.0)
                    if amount <= 0:
                        continue
                    amount_usd = amount * float(prices.get(symbol, 0.0) or 0.0)
                    if amount_usd <= 0:
                        continue

                    from_user = transfer.get("fromUserAccount")
                    to_user = transfer.get("toUserAccount")
                    signal = "NEUTRAL"

                    # For now, wallet-level semantics are proxy semantics:
                    # stablecoin receipt into user wallet = bullish inflow
                    # token receipt into user wallet = bullish outflow
                    if symbol in {"USDT", "USDC"}:
                        if to_user and not from_user:
                            signal = "BULLISH_INFLOW"
                        elif from_user and not to_user:
                            signal = "BEARISH_OUTFLOW"
                        else:
                            signal = "BULLISH_INFLOW" if transfer.get("toUserAccount") else "BEARISH_OUTFLOW"
                    else:
                        if to_user and not from_user:
                            signal = "BULLISH_OUTFLOW"
                        elif from_user and not to_user:
                            signal = "BEARISH_INFLOW"
                        else:
                            signal = "BULLISH_OUTFLOW" if transfer.get("toUserAccount") else "BEARISH_INFLOW"

                    all_events.append(
                        {
                            "hash": tx.get("signature"),
                            "timestamp": iso_utc(tx_dt),
                            "instrument": "SOL",
                            "symbol": symbol,
                            "amount_usd": amount_usd,
                            "signal": signal,
                        }
                    )

            before = rows[-1].get("signature")
            if stop_paging or not before:
                break
            time.sleep(0.15)

    return all_events


def aggregate_flow_4h(events: list[dict]) -> pd.DataFrame:
    rows = []
    for event in events:
        try:
            dt = parse_iso(event["timestamp"])
        except Exception:
            continue
        token_flow, stable_flow = classify_flow(event["signal"], event["symbol"], float(event["amount_usd"]))
        rows.append(
            {
                "datetime": bar_floor_4h(dt),
                "instrument": event["instrument"],
                "token_net_flow_4h": token_flow,
                "stablecoin_net_flow_4h": stable_flow,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["datetime", "instrument", "token_net_flow_4h", "stablecoin_net_flow_4h"])

    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["datetime", "instrument"], as_index=False)[["token_net_flow_4h", "stablecoin_net_flow_4h"]]
        .sum()
        .sort_values(["instrument", "datetime"])
    )
    for col in ["token_net_flow_4h", "stablecoin_net_flow_4h"]:
        agg[col.replace("_4h", "_24h")] = (
            agg.groupby("instrument")[col]
            .rolling(window=6, min_periods=1)
            .sum()
            .reset_index(level=0, drop=True)
        )
    return agg


def merge_into_feature_table(flow_df: pd.DataFrame) -> tuple[int, int]:
    features = pd.read_csv(CSV_PATH)
    features["datetime"] = pd.to_datetime(features["datetime"], utc=True)
    flow_df = flow_df.copy()
    flow_df["datetime"] = pd.to_datetime(flow_df["datetime"], utc=True)

    merged = features.merge(flow_df, on=["datetime", "instrument"], how="left", suffixes=("", "_new"))
    updated_rows = 0
    for col in [
        "token_net_flow_4h",
        "stablecoin_net_flow_4h",
        "token_net_flow_24h",
        "stablecoin_net_flow_24h",
    ]:
        new_col = f"{col}_new"
        if new_col not in merged:
            continue
        before = merged[col].notna().sum() if col in merged else 0
        merged[col] = merged[new_col].combine_first(merged[col] if col in merged else pd.Series(index=merged.index))
        after = merged[col].notna().sum()
        updated_rows += max(0, after - before)
        merged.drop(columns=[new_col], inplace=True)

    merged["datetime"] = merged["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    merged.to_csv(CSV_PATH, index=False)
    return len(flow_df), updated_rows


def save_flow_cache(flow_df: pd.DataFrame) -> None:
    out = flow_df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(CHAIN_FLOW_CACHE, index=False)


def main():
    parser = argparse.ArgumentParser(description="Backfill ETH/SOL chain flow history into 4H feature table.")
    parser.add_argument("--days", type=int, default=30, help="How many recent days to backfill.")
    parser.add_argument("--eth-pages", type=int, default=5, help="Max Etherscan pages per token.")
    parser.add_argument("--sol-pages", type=int, default=10, help="Max Moralis swap pages per token.")
    parser.add_argument("--eth-exchange-limit", type=int, default=6, help="How many exchange addresses to scan for ETH flow.")
    args = parser.parse_args()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)

    print(f"Backfilling chain flow from {iso_utc(start_dt)} to {iso_utc(end_dt)}")
    _ensure_csv_schema()

    eth_events = fetch_eth_historical_transfers(
        start_dt,
        end_dt,
        max_pages_per_token=args.eth_pages,
        exchange_limit=args.eth_exchange_limit,
    )
    print(f"ETH events: {len(eth_events)}")
    sol_events = fetch_sol_historical_transfers_helius(start_dt, end_dt, max_pages=args.sol_pages)
    if not sol_events:
        sol_events = fetch_sol_historical_swaps(start_dt, end_dt, max_pages_per_token=args.sol_pages)
    print(f"SOL events: {len(sol_events)}")

    flow_df = aggregate_flow_4h(eth_events + sol_events)
    if flow_df.empty:
        print("No chain flow rows produced.")
        return

    save_flow_cache(flow_df)
    flow_rows, updated_rows = merge_into_feature_table(flow_df)
    print(
        json.dumps(
            {
                "flow_rows": int(flow_rows),
                "updated_feature_rows": int(updated_rows),
                "instruments": sorted(flow_df["instrument"].unique().tolist()),
                "cache_path": str(CHAIN_FLOW_CACHE),
                "feature_path": str(CSV_PATH),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
