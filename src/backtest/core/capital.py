"""Capital tracking and position sizing for the Grade A+B capital simulation."""

import math


def compute_lot_count(premium: float, lot_size: int, capital_available: float, max_per_trade: float) -> int:
    """Determine how many lots to buy given capital constraints."""
    cost_per_lot = premium * lot_size
    if cost_per_lot <= 0:
        return 0
    deploy = min(capital_available, max_per_trade)
    return max(1, math.floor(deploy / cost_per_lot))


class PortfolioTracker:
    """Tracks a compounding portfolio with concurrent positions."""

    def __init__(self, starting_capital: float, max_per_trade: float):
        self.starting_capital = starting_capital
        self.max_per_trade = max_per_trade
        self.settled_capital = float(starting_capital)
        self.cumulative_pnl = 0.0
        self.active_positions: list[dict] = []

    def settle_closed(self, current_time):
        """Settle positions whose exit_time <= current_time."""
        still_active = []
        for pos in self.active_positions:
            if pos["exit_time"] <= current_time:
                self.settled_capital += pos["rupee_pnl"]
            else:
                still_active.append(pos)
        self.active_positions = still_active

    @property
    def locked_capital(self) -> float:
        return sum(p["capital_used"] for p in self.active_positions)

    @property
    def available_capital(self) -> float:
        return self.settled_capital - self.locked_capital

    @property
    def total_capital(self) -> float:
        return self.starting_capital + self.cumulative_pnl

    def open_position(self, capital_used: float, rupee_pnl: float, exit_time):
        self.active_positions.append({
            "exit_time": exit_time,
            "capital_used": capital_used,
            "rupee_pnl": rupee_pnl,
        })
        self.cumulative_pnl += rupee_pnl
