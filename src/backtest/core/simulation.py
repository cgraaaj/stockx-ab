"""Shared option trade simulation and RSI computation."""

from datetime import datetime

import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def get_premium_rsi_at_signal(
    candles: pd.DataFrame,
    signal_time,
    period: int = 14,
) -> float | None:
    mask = candles["time_stamp"] <= signal_time
    pre = candles.loc[mask]
    if len(pre) < period + 1:
        return None
    rsi_series = compute_rsi(pre["close"], period)
    return float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None


def simulate_option_trade(
    candles: pd.DataFrame,
    signal_time: datetime,
    entry_offset: int,
    sl_pct: float,
    target_pct: float,
    max_exit_time: str,
) -> dict | None:
    """Simulate a single option trade on premium candles.

    Returns dict with outcome, entry_premium, exit_premium, entry_time,
    exit_time, sl_premium, target_premium, holding_candles.
    Returns None if entry not possible.
    """
    max_exit_ts = datetime.strptime(
        f"{signal_time.strftime('%Y-%m-%d')} {max_exit_time}",
        "%Y-%m-%d %H:%M:%S",
    )

    signal_idx = candles[candles["time_stamp"] <= signal_time].index
    if signal_idx.empty:
        return None
    entry_idx = signal_idx[-1] + entry_offset
    if entry_idx >= len(candles):
        return None

    entry_row = candles.iloc[entry_idx]
    entry_premium = float(entry_row["open"])
    entry_time = entry_row["time_stamp"]

    if entry_premium <= 0:
        return None

    sl_premium = entry_premium * (1 - sl_pct / 100.0)
    target_premium = entry_premium * (1 + target_pct / 100.0)

    for i in range(entry_idx + 1, len(candles)):
        row = candles.iloc[i]
        ts = row["time_stamp"]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if ts >= max_exit_ts:
            return dict(
                outcome="time_exit", entry_premium=entry_premium,
                exit_premium=close, entry_time=entry_time, exit_time=ts,
                sl_premium=sl_premium, target_premium=target_premium,
                holding_candles=i - entry_idx,
            )

        if low <= sl_premium:
            return dict(
                outcome="sl_hit", entry_premium=entry_premium,
                exit_premium=sl_premium, entry_time=entry_time, exit_time=ts,
                sl_premium=sl_premium, target_premium=target_premium,
                holding_candles=i - entry_idx,
            )

        if high >= target_premium:
            return dict(
                outcome="target_hit", entry_premium=entry_premium,
                exit_premium=target_premium, entry_time=entry_time, exit_time=ts,
                sl_premium=sl_premium, target_premium=target_premium,
                holding_candles=i - entry_idx,
            )

    last = candles.iloc[-1]
    return dict(
        outcome="time_exit", entry_premium=entry_premium,
        exit_premium=float(last["close"]), entry_time=entry_time,
        exit_time=last["time_stamp"], sl_premium=sl_premium,
        target_premium=target_premium,
        holding_candles=len(candles) - 1 - entry_idx,
    )


def simulate_staged_entry_trade(
    candles: pd.DataFrame,
    signal_time: datetime,
    sl_pct: float,
    target_pct: float,
    max_exit_time: str,
    rsi_period: int = 14,
    rsi_entry_threshold: float = 60,
    vol_multiplier: float = 1.2,
    vol_lookback: int = 10,
    max_wait_candles: int = 60,
    entry_deadline: str = "14:00:00",
) -> dict | None:
    """Staged entry: scan forward from signal for RSI/volume confirmation."""
    date_str = signal_time.strftime("%Y-%m-%d")
    max_exit_ts = datetime.strptime(f"{date_str} {max_exit_time}", "%Y-%m-%d %H:%M:%S")
    deadline_ts = datetime.strptime(f"{date_str} {entry_deadline}", "%Y-%m-%d %H:%M:%S")

    signal_idx = candles[candles["time_stamp"] <= signal_time].index
    if signal_idx.empty:
        return None
    scan_start = signal_idx[-1] + 1
    if scan_start >= len(candles):
        return None

    rsi_full = compute_rsi(candles["close"], rsi_period)
    vol_series = candles["volume"].astype(float)

    entry_idx = None
    entry_reason = None
    candles_waited = 0

    for i in range(scan_start, len(candles)):
        ts = candles.iloc[i]["time_stamp"]

        if ts >= deadline_ts:
            return dict(
                outcome="no_entry", exit_premium=0, exit_time=str(ts),
                holding_candles=0, entry_premium=0, entry_time=str(ts),
                entry_reason="deadline_reached", candles_waited=candles_waited,
            )

        candles_waited += 1
        current_rsi = float(rsi_full.iloc[i]) if not pd.isna(rsi_full.iloc[i]) else 50.0

        lookback_start = max(0, i - vol_lookback)
        avg_vol = vol_series.iloc[lookback_start:i].mean() if i > lookback_start else 0
        current_vol = float(vol_series.iloc[i])
        vol_ok = avg_vol > 0 and current_vol >= vol_multiplier * avg_vol
        rsi_ok = current_rsi <= rsi_entry_threshold

        if rsi_ok and vol_ok:
            entry_idx = i
            entry_reason = "rsi_vol_confirmed"
            break
        if rsi_ok and candles_waited >= 5:
            entry_idx = i
            entry_reason = "rsi_confirmed"
            break
        if candles_waited >= max_wait_candles:
            entry_idx = i
            entry_reason = "max_wait_fallback"
            break

    if entry_idx is None:
        return None

    entry_row = candles.iloc[entry_idx]
    entry_premium = float(entry_row["open"])
    entry_time = entry_row["time_stamp"]

    if entry_premium <= 0:
        return None

    sl_premium = entry_premium * (1 - sl_pct / 100.0)
    target_premium = entry_premium * (1 + target_pct / 100.0)

    for i in range(entry_idx + 1, len(candles)):
        row = candles.iloc[i]
        ts = row["time_stamp"]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if ts >= max_exit_ts:
            return dict(
                outcome="time_exit", exit_premium=close, exit_time=str(ts),
                holding_candles=i - entry_idx, entry_premium=entry_premium,
                entry_time=str(entry_time), entry_reason=entry_reason,
                candles_waited=candles_waited,
            )
        if low <= sl_premium:
            return dict(
                outcome="sl_hit", exit_premium=sl_premium, exit_time=str(ts),
                holding_candles=i - entry_idx, entry_premium=entry_premium,
                entry_time=str(entry_time), entry_reason=entry_reason,
                candles_waited=candles_waited,
            )
        if high >= target_premium:
            return dict(
                outcome="target_hit", exit_premium=target_premium, exit_time=str(ts),
                holding_candles=i - entry_idx, entry_premium=entry_premium,
                entry_time=str(entry_time), entry_reason=entry_reason,
                candles_waited=candles_waited,
            )

    last = candles.iloc[-1]
    return dict(
        outcome="time_exit", exit_premium=float(last["close"]),
        exit_time=str(last["time_stamp"]),
        holding_candles=len(candles) - 1 - entry_idx,
        entry_premium=entry_premium, entry_time=str(entry_time),
        entry_reason=entry_reason, candles_waited=candles_waited,
    )
