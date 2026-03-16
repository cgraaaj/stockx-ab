"""Market context tagging and prediction filtering."""

from datetime import time as _time

from src.analysis.models.entities import StockPrediction


def extract_preds(date_entries, option_type):
    """Flatten date-grouped prediction entries into StockPrediction list."""
    preds = []
    for entry in date_entries:
        for sd in entry.get("stock_data", []):
            preds.append(StockPrediction(
                stock=sd["stock"], timestamp=sd["time_stamp"],
                grade=sd["grade"], option_type=option_type,
                tn_ratio=sd["tn_ratio"],
                bullish_count=sd["bullish_count"],
                bearish_count=sd["bearish_count"],
            ))
    return preds


def compute_trend_alignment(option_type, trend):
    """Determine alignment between option direction and market trend."""
    if trend == "neutral":
        return "neutral"
    if option_type == "call":
        return "along" if trend == "bullish" else "against"
    return "along" if trend == "bearish" else "against"


def filter_preds_per_date(preds, date_index_contexts, market_svc):
    """Tag each prediction with market_trend and trend_alignment (keep all)."""
    for pred in preds:
        pred_date = (
            pred.timestamp.strftime("%Y-%m-%d")
            if hasattr(pred.timestamp, "strftime")
            else str(pred.timestamp)[:10]
        )
        ctx = date_index_contexts.get(pred_date)
        if ctx is None:
            pred.market_trend = "neutral"
            pred.trend_alignment = "neutral"
            continue

        idx_name = market_svc.get_index_for_stock(pred.stock)
        idx_ctx = ctx.get(idx_name)
        if idx_ctx is None:
            pred.market_trend = "neutral"
            pred.trend_alignment = "neutral"
            continue

        trend = idx_ctx.trend
        pred.market_trend = trend
        pred.trend_alignment = compute_trend_alignment(pred.option_type, trend)

    return preds


def rebuild_entries(filtered, original_entries):
    """Rebuild date-grouped entries from tagged predictions."""
    trend_map = {(p.stock, p.timestamp): p for p in filtered}
    rebuilt = []
    for entry in original_entries:
        kept_data = []
        for sd in entry.get("stock_data", []):
            key = (sd["stock"], sd["time_stamp"])
            pred = trend_map.get(key)
            if pred is not None:
                sd["market_trend"] = pred.market_trend
                sd["trend_alignment"] = pred.trend_alignment
                kept_data.append(sd)
        if kept_data:
            rebuilt.append({**entry, "stock_data": kept_data})
    return rebuilt


def filter_by_cutoff(date_entries, cutoff_time_str):
    """Remove predictions whose signal time exceeds the cutoff."""
    parts = cutoff_time_str.split(":")
    cutoff = _time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    filtered = []
    for entry in date_entries:
        kept = [
            sd for sd in entry.get("stock_data", [])
            if sd["time_stamp"].time() <= cutoff
        ]
        if kept:
            filtered.append({**entry, "stock_data": kept})
    return filtered
