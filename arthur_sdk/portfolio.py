"""
Portfolio management for Arthur SDK.

Provides portfolio snapshots, exposure analysis, and risk metrics.

Example:
    from arthur_sdk import Arthur, Portfolio

    client = Arthur.from_credentials_file("creds.json")
    portfolio = Portfolio(client)
    print(portfolio.snapshot())
    print(portfolio.exposure())
    print(portfolio.risk_metrics())
"""

import time
import threading
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("arthur_sdk.portfolio")


class Portfolio:
    """
    Portfolio management wrapper around Arthur client.

    Provides high-level portfolio analysis including snapshots,
    exposure tracking, risk metrics, and equity history.

    Args:
        client: An authenticated Arthur client instance.

    Example:
        portfolio = Portfolio(client)
        snap = portfolio.snapshot()
        print(f"Equity: ${snap['equity']:.2f}")
        print(f"Positions: {snap['num_positions']}")
    """

    def __init__(self, client):
        """
        Initialize Portfolio with an Arthur client.

        Args:
            client: Authenticated Arthur client instance.
        """
        self.client = client
        self._equity_history: List[Dict[str, Any]] = []
        self._history_lock = threading.Lock()
        self._record_equity()

    def _record_equity(self):
        """Record current equity to history."""
        try:
            eq = self.client.equity()
            with self._history_lock:
                self._equity_history.append({
                    "timestamp": time.time(),
                    "equity": eq,
                })
                # Keep max 8640 entries (~24h at 10s intervals, or ~30 days of hourly)
                if len(self._equity_history) > 8640:
                    self._equity_history = self._equity_history[-8640:]
        except Exception as e:
            logger.debug(f"Failed to record equity: {e}")

    def snapshot(self) -> Dict[str, Any]:
        """
        Get a full portfolio snapshot.

        Returns:
            Dict containing:
                - equity: Total account equity in USDC
                - balance: Available USDC balance
                - unrealized_pnl: Total unrealized PnL
                - num_positions: Number of open positions
                - positions: List of position details
                - margin_usage: Estimated margin usage ratio
                - timestamp: Snapshot timestamp
        """
        self._record_equity()
        positions = self.client.positions()
        balance = self.client.balance()
        equity = self.client.equity()
        total_pnl = sum(p.unrealized_pnl for p in positions)

        # Estimate margin usage from position notional vs equity
        total_notional = sum(p.size * p.mark_price for p in positions)
        margin_usage = (total_notional / equity) if equity > 0 else 0.0

        return {
            "equity": equity,
            "balance": balance,
            "unrealized_pnl": total_pnl,
            "num_positions": len(positions),
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "mark_price": p.mark_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "pnl_percent": p.pnl_percent,
                    "leverage": p.leverage,
                    "notional_usd": p.size * p.mark_price,
                }
                for p in positions
            ],
            "margin_usage": margin_usage,
            "timestamp": time.time(),
        }

    def exposure(self) -> Dict[str, Any]:
        """
        Get net long/short exposure in USD.

        Returns:
            Dict containing:
                - long_usd: Total long exposure in USD
                - short_usd: Total short exposure in USD
                - net_usd: Net exposure (long - short) in USD
                - gross_usd: Gross exposure (long + short) in USD
                - by_symbol: Per-symbol exposure breakdown
        """
        positions = self.client.positions()
        long_usd = 0.0
        short_usd = 0.0
        by_symbol = {}

        for p in positions:
            notional = p.size * p.mark_price
            if p.side == "LONG":
                long_usd += notional
                by_symbol[p.symbol] = notional
            else:
                short_usd += notional
                by_symbol[p.symbol] = -notional

        return {
            "long_usd": long_usd,
            "short_usd": short_usd,
            "net_usd": long_usd - short_usd,
            "gross_usd": long_usd + short_usd,
            "by_symbol": by_symbol,
        }

    def risk_metrics(self) -> Dict[str, Any]:
        """
        Get portfolio risk metrics.

        Returns:
            Dict containing:
                - margin_usage_pct: Margin usage as percentage
                - max_drawdown_pct: Maximum drawdown from peak equity (from history)
                - sharpe_estimate: Simple Sharpe ratio estimate from equity returns
                - equity: Current equity
                - num_positions: Number of open positions
        """
        self._record_equity()
        equity = self.client.equity()
        positions = self.client.positions()

        # Margin usage
        total_notional = sum(p.size * p.mark_price for p in positions)
        margin_usage_pct = (total_notional / equity * 100) if equity > 0 else 0.0

        # Max drawdown from history
        max_drawdown_pct = 0.0
        with self._history_lock:
            if len(self._equity_history) >= 2:
                peak = self._equity_history[0]["equity"]
                for entry in self._equity_history:
                    eq = entry["equity"]
                    if eq > peak:
                        peak = eq
                    if peak > 0:
                        dd = (peak - eq) / peak * 100
                        if dd > max_drawdown_pct:
                            max_drawdown_pct = dd

        # Simple Sharpe estimate from equity returns
        sharpe_estimate = 0.0
        with self._history_lock:
            if len(self._equity_history) >= 3:
                returns = []
                for i in range(1, len(self._equity_history)):
                    prev = self._equity_history[i - 1]["equity"]
                    curr = self._equity_history[i]["equity"]
                    if prev > 0:
                        returns.append((curr - prev) / prev)
                if returns:
                    mean_ret = sum(returns) / len(returns)
                    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
                    std_ret = variance ** 0.5
                    if std_ret > 0:
                        sharpe_estimate = mean_ret / std_ret

        return {
            "margin_usage_pct": margin_usage_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "sharpe_estimate": sharpe_estimate,
            "equity": equity,
            "num_positions": len(positions),
        }

    def history(self, hours: float = 24) -> List[Dict[str, Any]]:
        """
        Get equity curve from periodic snapshots (in-memory).

        Note: History is only available from when this Portfolio instance
        was created. Call snapshot() or risk_metrics() periodically to
        build up history.

        Args:
            hours: Number of hours of history to return (default 24).

        Returns:
            List of dicts with 'timestamp' and 'equity' keys.
        """
        self._record_equity()
        cutoff = time.time() - (hours * 3600)
        with self._history_lock:
            return [
                entry for entry in self._equity_history
                if entry["timestamp"] >= cutoff
            ]

    def __repr__(self) -> str:
        return f"Portfolio(client={self.client!r})"
