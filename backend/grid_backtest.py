from dataclasses import asdict, dataclass
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union


PriceBar = Union[float, int, Mapping[str, Any]]


@dataclass
class GridBacktestConfig:
    lower_bound: float
    upper_bound: float
    grid_count: int
    leverage: float = 3.0
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0007
    per_grid_notional: float = 100.0
    initial_base_ratio: float = 0.5
    stop_on_breakout: bool = True
    breakout_buffer_pct: float = 0.0
    consecutive_outside_bars_to_stop: int = 2
    take_profit_pct: Optional[float] = 0.04
    stop_loss_pct: Optional[float] = -0.12
    trailing_take_profit_drawdown_pct: Optional[float] = 0.20
    min_trailing_profit_pct: float = 0.02
    max_bars: Optional[int] = None
    funding_rate_per_bar: float = 0.0
    maintenance_margin_rate: float = 0.005


def _crossed_levels(prev_price: float, curr_price: float, levels: List[float]) -> List[float]:
    if prev_price == curr_price:
        return []
    low = min(prev_price, curr_price)
    high = max(prev_price, curr_price)
    crossed = [level for level in levels if low < level <= high]
    return crossed if curr_price > prev_price else list(reversed(crossed))


def _normalize_bar(raw_bar: PriceBar, prev_close: Optional[float] = None) -> Dict[str, float]:
    if isinstance(raw_bar, Mapping):
        close = float(raw_bar.get("close", raw_bar.get("c", prev_close or 0.0)))
        open_price = float(raw_bar.get("open", raw_bar.get("o", prev_close if prev_close is not None else close)))
        high = float(raw_bar.get("high", raw_bar.get("h", max(open_price, close))))
        low = float(raw_bar.get("low", raw_bar.get("l", min(open_price, close))))
        return {
            "open": open_price,
            "high": max(high, open_price, close),
            "low": min(low, open_price, close),
            "close": close,
        }

    price = float(raw_bar)
    return {"open": price, "high": price, "low": price, "close": price}


def _bar_path(prev_close: float, bar: Dict[str, float]) -> List[float]:
    open_price = bar["open"] if bar["open"] > 0 else prev_close
    if bar["close"] >= open_price:
        raw_path = [prev_close, open_price, bar["low"], bar["high"], bar["close"]]
    else:
        raw_path = [prev_close, open_price, bar["high"], bar["low"], bar["close"]]

    path: List[float] = []
    for price in raw_path:
        if not path or abs(path[-1] - price) > 1e-12:
            path.append(price)
    return path


def _all_crosses(bars: List[Dict[str, float]], inner_levels: List[float]) -> int:
    crosses = 0
    for i in range(1, len(bars)):
        path = _bar_path(bars[i - 1]["close"], bars[i])
        for j in range(1, len(path)):
            crosses += len(_crossed_levels(path[j - 1], path[j], inner_levels))
    return crosses


def _next_higher_level(level: float, levels: List[float]) -> Optional[float]:
    for candidate in levels:
        if candidate > level:
            return candidate
    return None


def run_grid_backtest(price_series: List[PriceBar], config: GridBacktestConfig) -> Dict[str, Any]:
    """
    Neutral-grid backtest focused on realistic risk-adjusted rotation quality.

    Assumptions:
    - The bot runs inside a fixed range and reacts whenever price crosses a grid level.
    - Downward crossing buys one grid clip; upward crossing sells one grid clip.
    - Each clip uses `per_grid_notional`.
    - Inventory is tracked as paired lots: a downward fill creates a sell order one grid higher.
    - Float price input is treated as close-only. Dict input can provide open/high/low/close.
    - Leverage affects margin, return and liquidation-risk metrics, not fill notional.
    """
    lower = float(config.lower_bound)
    upper = float(config.upper_bound)
    grid_count = max(int(config.grid_count), 1)
    price_points = len(price_series)

    if price_points < 2 or upper <= lower or grid_count < 2:
        return {
            "strategy_family": "GRID",
            "implemented": True,
            "valid": False,
            "price_points": price_points,
            "reason": "insufficient_inputs",
        }

    bars: List[Dict[str, float]] = []
    prev_close: Optional[float] = None
    for raw_bar in price_series:
        bar = _normalize_bar(raw_bar, prev_close)
        bars.append(bar)
        prev_close = bar["close"]

    levels = [lower + (upper - lower) * i / grid_count for i in range(grid_count + 1)]
    inner_levels = levels[1:-1]
    capital_grid_count = max(grid_count, 1)
    mid_price = (lower + upper) / 2.0
    fee_rate = float(config.fee_rate)
    slippage_rate = float(config.slippage_rate)
    leverage = max(float(config.leverage), 1e-9)
    per_grid_notional = float(config.per_grid_notional)

    initial_notional = capital_grid_count * per_grid_notional
    initial_margin = initial_notional / leverage
    initial_base_ratio = min(max(float(config.initial_base_ratio), 0.0), 1.0)
    initial_quote_cash = initial_notional * (1.0 - initial_base_ratio)
    initial_base_notional = initial_notional * initial_base_ratio
    initial_sell_targets = [level for level in inner_levels if level > mid_price]
    if not initial_sell_targets and inner_levels:
        initial_sell_targets = [inner_levels[-1]]

    lots_by_sell_level: Dict[float, List[Dict[str, float]]] = {level: [] for level in levels}
    initial_base_qty = 0.0
    initial_base_cost = 0.0
    if initial_base_notional > 0 and initial_sell_targets:
        per_target_cost = initial_base_notional / len(initial_sell_targets)
        for target in initial_sell_targets:
            qty = per_target_cost / max(mid_price, 1e-9)
            lots_by_sell_level.setdefault(target, []).append({"qty": qty, "cost": per_target_cost})
            initial_base_qty += qty
            initial_base_cost += per_target_cost

    quote_cash = initial_quote_cash
    inventory_qty = initial_base_qty
    inventory_cost = initial_base_cost
    initial_inventory_qty = inventory_qty
    initial_inventory_value = inventory_qty * mid_price

    realized_pnl = 0.0
    gross_realized_pnl = 0.0
    fees_paid = 0.0
    slippage_cost = 0.0
    funding_paid = 0.0
    buy_fills = 0
    sell_fills = 0
    skipped_buys = 0
    skipped_sells = 0
    breakout_exit = None
    exit_reason = None
    max_inventory_value = initial_inventory_value
    min_inventory_value = initial_inventory_value
    peak_equity = initial_margin
    max_drawdown_pct = 0.0
    outside_close_count = 0
    bars_processed = 0

    def floating_pnl(mark_price: float) -> float:
        return inventory_qty * mark_price - inventory_cost

    def margin_equity(mark_price: float) -> float:
        return initial_margin + realized_pnl + floating_pnl(mark_price)

    def update_drawdown(mark_price: float) -> float:
        nonlocal peak_equity, max_drawdown_pct
        equity = margin_equity(mark_price)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_equity - equity) / peak_equity)
        return equity

    def force_exit(mark_price: float) -> float:
        nonlocal inventory_qty, inventory_cost, quote_cash, realized_pnl, gross_realized_pnl, fees_paid, slippage_cost
        if inventory_qty <= 0:
            return 0.0
        gross_value = inventory_qty * mark_price
        fee = gross_value * fee_rate
        slip = gross_value * slippage_rate
        net_value = gross_value - fee - slip
        qty = inventory_qty
        quote_cash += net_value
        realized_pnl += net_value - inventory_cost
        gross_realized_pnl += gross_value - inventory_cost
        fees_paid += fee
        slippage_cost += slip
        inventory_qty = 0.0
        inventory_cost = 0.0
        return qty

    lower_stop = lower * (1.0 - max(float(config.breakout_buffer_pct), 0.0))
    upper_stop = upper * (1.0 + max(float(config.breakout_buffer_pct), 0.0))

    for bar_index in range(1, len(bars)):
        bar = bars[bar_index]
        path = _bar_path(bars[bar_index - 1]["close"], bar)
        bars_processed += 1

        for path_index in range(1, len(path)):
            prev_price = path[path_index - 1]
            curr_price = path[path_index]

            if config.stop_on_breakout and curr_price > upper_stop:
                breakout_exit = "upper_breakout"
                exit_reason = "SL_REACHED"
                break
            if config.stop_on_breakout and curr_price < lower_stop:
                breakout_exit = "lower_breakout"
                exit_reason = "SL_REACHED"
                break

            for level in _crossed_levels(prev_price, curr_price, inner_levels):
                clip_notional = per_grid_notional
                fee = clip_notional * fee_rate
                slip = clip_notional * slippage_rate

                if curr_price < prev_price:
                    total_spend = clip_notional + fee + slip
                    if quote_cash + 1e-9 < total_spend:
                        skipped_buys += 1
                        continue
                    qty = clip_notional / max(level, 1e-9)
                    sell_target = _next_higher_level(level, levels)
                    if sell_target is None:
                        skipped_buys += 1
                        continue
                    quote_cash -= total_spend
                    inventory_qty += qty
                    inventory_cost += clip_notional + fee + slip
                    lots_by_sell_level.setdefault(sell_target, []).append({"qty": qty, "cost": clip_notional + fee + slip})
                    fees_paid += fee
                    slippage_cost += slip
                    buy_fills += 1
                else:
                    lots = lots_by_sell_level.setdefault(level, [])
                    if not lots:
                        skipped_sells += 1
                        continue
                    lot = lots.pop(0)
                    qty = lot["qty"]
                    if inventory_qty + 1e-9 < qty:
                        skipped_sells += 1
                        lots.insert(0, lot)
                        continue
                    cost_basis = lot["cost"]
                    gross_proceeds = qty * level
                    fee = gross_proceeds * fee_rate
                    slip = gross_proceeds * slippage_rate
                    net_proceeds = gross_proceeds - fee - slip
                    quote_cash += net_proceeds
                    inventory_qty -= qty
                    inventory_cost = max(inventory_cost - cost_basis, 0.0)
                    fees_paid += fee
                    slippage_cost += slip
                    gross_realized_pnl += gross_proceeds - cost_basis
                    realized_pnl += net_proceeds - cost_basis
                    sell_fills += 1

                inventory_value = inventory_qty * curr_price
                max_inventory_value = max(max_inventory_value, inventory_value)
                min_inventory_value = min(min_inventory_value, inventory_value)
                update_drawdown(curr_price)

            if exit_reason:
                break

        final_bar_price = bar["close"]
        if not exit_reason and config.funding_rate_per_bar:
            funding = abs(inventory_qty * final_bar_price) * float(config.funding_rate_per_bar)
            quote_cash -= funding
            realized_pnl -= funding
            funding_paid += funding

        equity = update_drawdown(final_bar_price)
        maintenance_margin = abs(inventory_qty * final_bar_price) * max(float(config.maintenance_margin_rate), 0.0)

        if not exit_reason and maintenance_margin > 0 and equity <= maintenance_margin:
            breakout_exit = "liquidation_risk"
            exit_reason = "LIQUIDATION_RISK"

        if not exit_reason:
            if final_bar_price > upper or final_bar_price < lower:
                outside_close_count += 1
            else:
                outside_close_count = 0
            if outside_close_count >= max(int(config.consecutive_outside_bars_to_stop), 1):
                breakout_exit = "range_invalidated"
                exit_reason = "RANGE_INVALIDATED"

        pnl_on_margin = (equity - initial_margin) / initial_margin if initial_margin > 0 else 0.0
        if not exit_reason and config.take_profit_pct is not None and pnl_on_margin >= float(config.take_profit_pct):
            breakout_exit = "take_profit"
            exit_reason = "TP_REACHED"
        if not exit_reason and config.stop_loss_pct is not None and pnl_on_margin <= float(config.stop_loss_pct):
            breakout_exit = "stop_loss"
            exit_reason = "SL_REACHED"
        if (
            not exit_reason
            and config.trailing_take_profit_drawdown_pct is not None
            and peak_equity >= initial_margin * (1.0 + max(float(config.min_trailing_profit_pct), 0.0))
            and peak_equity > 0
            and (peak_equity - equity) / peak_equity >= float(config.trailing_take_profit_drawdown_pct)
        ):
            breakout_exit = "trailing_take_profit"
            exit_reason = "TP_REACHED"
        if not exit_reason and config.max_bars is not None and bars_processed >= int(config.max_bars):
            breakout_exit = "time_stop"
            exit_reason = "TIME_STOP"

        if exit_reason:
            break

    final_price = bars[min(bars_processed, len(bars) - 1)]["close"] if exit_reason else bars[-1]["close"]
    forced_exit_qty = 0.0
    if breakout_exit:
        forced_exit_qty = force_exit(final_price)

    floating_inventory_pnl = inventory_qty * final_price - inventory_cost
    initial_capital = initial_quote_cash + initial_inventory_value
    ending_equity = quote_cash + inventory_qty * final_price
    net_total_pnl = ending_equity - initial_capital
    inventory_drift_value = inventory_qty * final_price - initial_inventory_value
    inventory_drift_ratio = 0.0 if initial_capital <= 0 else abs(inventory_drift_value) / initial_capital
    fill_count = buy_fills + sell_fills
    theoretical_crosses = _all_crosses(bars, inner_levels)
    range_capture_efficiency = 0.0 if theoretical_crosses <= 0 else fill_count / theoretical_crosses
    avg_profit_per_fill = 0.0 if fill_count <= 0 else realized_pnl / fill_count
    fee_drag_ratio = 0.0 if abs(gross_realized_pnl) <= 1e-9 else (fees_paid + slippage_cost) / max(abs(gross_realized_pnl), 1e-9)
    final_margin_equity = initial_margin + net_total_pnl

    return {
        "strategy_family": "GRID",
        "implemented": True,
        "valid": True,
        "price_points": price_points,
        "config": {
            "lower_bound": lower,
            "upper_bound": upper,
            "grid_count": grid_count,
            "leverage": float(config.leverage),
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "per_grid_notional": per_grid_notional,
            "funding_rate_per_bar": float(config.funding_rate_per_bar),
            "take_profit_pct": config.take_profit_pct,
            "stop_loss_pct": config.stop_loss_pct,
            "max_bars": config.max_bars,
        },
        "summary": {
            "breakout_exit": breakout_exit,
            "exit_reason": exit_reason,
            "fill_count": fill_count,
            "buy_fills": buy_fills,
            "sell_fills": sell_fills,
            "skipped_buys": skipped_buys,
            "skipped_sells": skipped_sells,
            "forced_exit_qty": round(forced_exit_qty, 8),
            "bars_processed": bars_processed,
            "outside_close_count": outside_close_count,
        },
        "metrics": {
            "gross_realized_pnl": round(gross_realized_pnl, 4),
            "net_realized_pnl": round(realized_pnl, 4),
            "net_total_pnl": round(net_total_pnl, 4),
            "floating_inventory_pnl": round(floating_inventory_pnl, 4),
            "fees_paid": round(fees_paid, 4),
            "slippage_cost": round(slippage_cost, 4),
            "funding_paid": round(funding_paid, 4),
            "fee_drag_ratio": round(fee_drag_ratio, 4),
            "avg_profit_per_fill": round(avg_profit_per_fill, 6),
            "range_capture_efficiency": round(range_capture_efficiency, 4),
            "inventory_drift_ratio": round(inventory_drift_ratio, 4),
            "inventory_value_min": round(min_inventory_value, 4),
            "inventory_value_max": round(max_inventory_value, 4),
            "ending_equity": round(ending_equity, 4),
            "initial_capital": round(initial_capital, 4),
            "initial_margin": round(initial_margin, 4),
            "final_margin_equity": round(final_margin_equity, 4),
            "peak_margin_equity": round(peak_equity, 4),
            "max_drawdown_pct": round(max_drawdown_pct * 100.0, 4),
            "return_on_capital_pct": round((net_total_pnl / initial_capital) * 100.0, 4) if initial_capital > 0 else 0.0,
            "return_on_margin_pct": round((net_total_pnl / initial_margin) * 100.0, 4) if initial_margin > 0 else 0.0,
        },
    }


def scan_grid_parameters(
    price_series: List[PriceBar],
    *,
    lower_bound: float,
    upper_bound: float,
    grid_counts: Iterable[int],
    fee_rates: Iterable[float],
    slippage_rates: Iterable[float],
    per_grid_notionals: Iterable[float],
    leverage_values: Optional[Iterable[float]] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Run a parameter sweep over a single price window and rank candidates by
    return on margin, drawdown, fee drag and inventory drift quality.
    """
    leverage_values = list(leverage_values or [3.0])
    results: List[Dict[str, Any]] = []

    for grid_count, fee_rate, slippage_rate, per_grid_notional, leverage in product(
        grid_counts,
        fee_rates,
        slippage_rates,
        per_grid_notionals,
        leverage_values,
    ):
        config = GridBacktestConfig(
            lower_bound=float(lower_bound),
            upper_bound=float(upper_bound),
            grid_count=int(grid_count),
            leverage=float(leverage),
            fee_rate=float(fee_rate),
            slippage_rate=float(slippage_rate),
            per_grid_notional=float(per_grid_notional),
        )
        run = run_grid_backtest(price_series, config)
        if not run.get("valid"):
            continue
        metrics = run.get("metrics", {}) or {}
        results.append(
            {
                "config": asdict(config),
                "summary": run.get("summary", {}),
                "metrics": metrics,
                "score": (
                    float(metrics.get("return_on_margin_pct", metrics.get("return_on_capital_pct", 0.0))),
                    -float(metrics.get("max_drawdown_pct", 0.0)),
                    -float(metrics.get("fee_drag_ratio", 0.0)),
                    -float(metrics.get("inventory_drift_ratio", 0.0)),
                ),
            }
        )

    ranked = sorted(results, key=lambda item: item["score"], reverse=True)
    return {
        "strategy_family": "GRID",
        "window": {
            "price_points": len(price_series),
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
        },
        "tested": len(results),
        "top_results": ranked[: max(int(top_k), 1)],
    }
