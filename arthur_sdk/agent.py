"""
Agent API for Arthur SDK — the star of v0.3.0.

The Agent class wraps the Arthur client with risk guardrails and
strategy primitives for autonomous trading.

Example:
    from arthur_sdk import Arthur, Agent

    client = Arthur.from_credentials_file("creds.json")
    agent = Agent(client, max_drawdown=0.10, max_position_usd=10000)

    agent.twap("ETH", "BUY", total_usd=5000, duration=300)
    agent.grid("ETH", lower=1900, upper=2100, levels=5, size_per_level=0.1)
    agent.rebalance({"ETH": 0.6, "BTC": 0.4})
"""

import time
import logging
import threading
from typing import Optional, Dict, List, Any, Callable

from .portfolio import Portfolio
from .exceptions import ArthurError, OrderError

logger = logging.getLogger("arthur_sdk.agent")


class Agent:
    """
    Autonomous trading agent with risk guardrails and strategy primitives.

    Wraps an Arthur client with:
    - Automatic risk checks before every trade
    - Max drawdown kill-switch
    - Per-symbol position limits
    - Strategy methods: TWAP, grid, rebalance, scale-in, DCA
    - Event callbacks for fills, liquidations, drawdowns

    Args:
        client: Authenticated Arthur client instance.
        max_drawdown: Maximum allowed drawdown as a fraction (e.g., 0.10 = 10%).
            If equity drops below (1 - max_drawdown) * initial_equity, all
            positions are closed and trading is halted.
        max_position_usd: Maximum position size per symbol in USD.

    Example:
        agent = Agent(client, max_drawdown=0.10, max_position_usd=10000)
        agent.on("drawdown", lambda data: print(f"DRAWDOWN: {data}"))
        agent.twap("ETH", "BUY", total_usd=1000, duration=60)
    """

    def __init__(
        self,
        client,
        max_drawdown: float = 0.15,
        max_position_usd: float = 50000,
    ):
        """
        Initialize the Agent.

        Args:
            client: Authenticated Arthur client instance.
            max_drawdown: Max drawdown fraction before kill-switch (default 0.15).
            max_position_usd: Max position USD per symbol (default 50000).
        """
        self.client = client
        self.max_drawdown = max_drawdown
        self.max_position_usd = max_position_usd
        self.portfolio = Portfolio(client)

        self._initial_equity = client.equity()
        self._peak_equity = self._initial_equity
        self._halted = False
        self._halt_reason: Optional[str] = None
        self._callbacks: Dict[str, List[Callable]] = {
            "fill": [],
            "liquidation": [],
            "drawdown": [],
        }
        self._active_threads: List[threading.Thread] = []
        self._lock = threading.Lock()

    # ==================== Event System ====================

    def on(self, event: str, callback: Callable) -> "Agent":
        """
        Register an event callback.

        Args:
            event: Event type — 'fill', 'liquidation', or 'drawdown'.
            callback: Function to call with event data dict.

        Returns:
            Self for chaining.
        """
        if event not in self._callbacks:
            raise ValueError(
                f"Unknown event '{event}'. Valid: {list(self._callbacks.keys())}"
            )
        self._callbacks[event].append(callback)
        return self

    def _emit(self, event: str, data: Any):
        """Dispatch an event to registered callbacks."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")

    # ==================== Risk Management ====================

    def risk_check(self, symbol: str = "", additional_usd: float = 0) -> bool:
        """
        Perform risk checks. Called automatically before every trade.

        Checks:
        1. Agent not halted
        2. Drawdown within limits
        3. Position size within limits (if symbol provided)

        Args:
            symbol: Symbol to check position limits for.
            additional_usd: Additional USD exposure being added.

        Returns:
            True if trade is allowed.

        Raises:
            ArthurError: If risk check fails.
        """
        if self._halted:
            raise ArthurError(
                f"Agent halted: {self._halt_reason}. "
                "Call agent.resume() to re-enable trading."
            )

        # Check drawdown
        current_equity = self.client.equity()
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        if self._peak_equity > 0:
            drawdown = (self._peak_equity - current_equity) / self._peak_equity
            if drawdown >= self.max_drawdown:
                self._halt("max_drawdown", drawdown)
                self._emit("drawdown", {
                    "drawdown": drawdown,
                    "peak_equity": self._peak_equity,
                    "current_equity": current_equity,
                    "threshold": self.max_drawdown,
                })
                # Emergency close
                try:
                    self.client.close_all()
                    logger.warning("Kill-switch triggered: all positions closed")
                except Exception as e:
                    logger.error(f"Failed to close positions on kill-switch: {e}")
                raise ArthurError(
                    f"Max drawdown exceeded: {drawdown:.1%} >= {self.max_drawdown:.1%}. "
                    "All positions closed."
                )

        # Check position limits
        if symbol and self.max_position_usd > 0:
            pos = self.client.position(symbol)
            current_notional = 0
            if pos:
                current_notional = pos.size * pos.mark_price
            if current_notional + additional_usd > self.max_position_usd:
                raise OrderError(
                    f"Position limit exceeded for {symbol}: "
                    f"${current_notional + additional_usd:.0f} > "
                    f"${self.max_position_usd:.0f}"
                )

        return True

    def _halt(self, reason: str, value: Any = None):
        """Halt the agent."""
        self._halted = True
        self._halt_reason = f"{reason}={value}" if value else reason
        logger.warning(f"Agent halted: {self._halt_reason}")

    def resume(self):
        """Resume trading after a halt. Resets peak equity to current."""
        self._halted = False
        self._halt_reason = None
        self._peak_equity = self.client.equity()
        logger.info("Agent resumed")

    @property
    def halted(self) -> bool:
        """Whether the agent is currently halted."""
        return self._halted

    # ==================== Strategy Primitives ====================

    def twap(
        self,
        symbol: str,
        side: str,
        total_usd: float,
        duration: float,
        slices: int = 10,
    ) -> threading.Thread:
        """
        Execute a TWAP (Time-Weighted Average Price) order.

        Splits the total order into equal slices executed at regular intervals.

        Args:
            symbol: Token symbol (e.g., "ETH").
            side: "BUY" or "SELL".
            total_usd: Total USD amount to execute.
            duration: Total execution time in seconds.
            slices: Number of slices (default 10).

        Returns:
            The background thread executing the TWAP.

        Example:
            # Buy $5000 ETH over 5 minutes in 10 slices
            agent.twap("ETH", "BUY", total_usd=5000, duration=300, slices=10)
        """
        self.risk_check(symbol, total_usd)
        usd_per_slice = total_usd / slices
        interval = duration / slices

        def _run():
            for i in range(slices):
                try:
                    self.risk_check(symbol, usd_per_slice)
                    if side.upper() == "BUY":
                        order = self.client.buy(symbol, usd=usd_per_slice)
                    else:
                        order = self.client.sell(symbol, usd=usd_per_slice)
                    self._emit("fill", {
                        "strategy": "twap",
                        "slice": i + 1,
                        "total_slices": slices,
                        "order": order,
                    })
                    logger.info(f"TWAP {symbol} slice {i+1}/{slices}: ${usd_per_slice:.0f}")
                except ArthurError as e:
                    logger.error(f"TWAP {symbol} slice {i+1} failed: {e}")
                    if self._halted:
                        break

                if i < slices - 1:
                    time.sleep(interval)

        t = threading.Thread(target=_run, daemon=True, name=f"twap-{symbol}")
        t.start()
        with self._lock:
            self._active_threads.append(t)
        return t

    def grid(
        self,
        symbol: str,
        lower: float,
        upper: float,
        levels: int,
        size_per_level: float,
    ) -> List[Any]:
        """
        Place a grid of limit orders.

        Places buy orders below mid and sell orders above mid,
        evenly spaced between lower and upper.

        Args:
            symbol: Token symbol.
            lower: Lower price bound.
            upper: Upper price bound.
            levels: Number of grid levels.
            size_per_level: Size per order in base asset.

        Returns:
            List of Order objects placed.

        Example:
            # ETH grid from $1900-$2100 with 5 levels
            agent.grid("ETH", lower=1900, upper=2100, levels=5, size_per_level=0.1)
        """
        if levels < 2:
            raise OrderError("Grid needs at least 2 levels")

        total_notional_est = size_per_level * ((lower + upper) / 2) * levels
        self.risk_check(symbol, total_notional_est)

        step = (upper - lower) / (levels - 1)
        mid = (lower + upper) / 2
        orders = []

        for i in range(levels):
            price = lower + step * i
            try:
                if price < mid:
                    order = self.client.limit_buy(symbol, price=price, size=size_per_level)
                else:
                    order = self.client.limit_sell(symbol, price=price, size=size_per_level)
                orders.append(order)
                logger.info(f"Grid {symbol}: {'BUY' if price < mid else 'SELL'} @ {price:.2f}")
            except Exception as e:
                logger.error(f"Grid order at {price:.2f} failed: {e}")

        return orders

    def rebalance(self, targets: Dict[str, float]) -> List[Any]:
        """
        Rebalance portfolio to target weights.

        Calculates the difference between current and target allocations,
        then places market orders to reach the targets.

        Args:
            targets: Dict mapping symbol to target weight (0.0-1.0).
                Weights should sum to <= 1.0.

        Returns:
            List of Order objects placed.

        Example:
            # Rebalance to 60% ETH, 40% BTC
            agent.rebalance({"ETH": 0.6, "BTC": 0.4})
        """
        total_weight = sum(targets.values())
        if total_weight > 1.001:
            raise OrderError(f"Target weights sum to {total_weight:.3f}, must be <= 1.0")

        equity = self.client.equity()
        positions = self.client.positions()
        current = {}
        for pos in positions:
            short_name = pos.symbol.replace("PERP_", "").replace("_USDC", "")
            notional = pos.size * pos.mark_price
            if pos.side == "SHORT":
                notional = -notional
            current[short_name] = notional

        orders = []
        for symbol, target_weight in targets.items():
            target_usd = equity * target_weight
            current_usd = current.get(symbol.upper(), 0)
            diff = target_usd - current_usd

            if abs(diff) < 1:  # Skip tiny adjustments
                continue

            try:
                self.risk_check(symbol, abs(diff))
                if diff > 0:
                    order = self.client.buy(symbol, usd=abs(diff))
                else:
                    order = self.client.sell(symbol, usd=abs(diff))
                orders.append(order)
                logger.info(f"Rebalance {symbol}: {'BUY' if diff > 0 else 'SELL'} ${abs(diff):.0f}")
            except Exception as e:
                logger.error(f"Rebalance {symbol} failed: {e}")

        # Close positions for symbols not in targets
        for pos in positions:
            short_name = pos.symbol.replace("PERP_", "").replace("_USDC", "")
            if short_name not in {s.upper() for s in targets}:
                try:
                    order = self.client.close(pos.symbol)
                    if order:
                        orders.append(order)
                        logger.info(f"Rebalance: closed {short_name} (not in targets)")
                except Exception as e:
                    logger.error(f"Failed to close {short_name}: {e}")

        return orders

    def scale_in(
        self,
        symbol: str,
        side: str,
        total_usd: float,
        entries: List[float],
    ) -> List[Any]:
        """
        Place scaled limit orders at multiple price levels.

        Splits total_usd evenly across the given entry prices.

        Args:
            symbol: Token symbol.
            side: "BUY" or "SELL".
            total_usd: Total USD amount to deploy.
            entries: List of limit prices for each entry.

        Returns:
            List of Order objects placed.

        Example:
            # Scale into ETH longs at 3 levels
            agent.scale_in("ETH", "BUY", total_usd=3000, entries=[1950, 1900, 1850])
        """
        if not entries:
            raise OrderError("Must provide at least one entry price")

        self.risk_check(symbol, total_usd)
        usd_per_entry = total_usd / len(entries)
        orders = []

        for price in entries:
            size = usd_per_entry / price
            try:
                if side.upper() == "BUY":
                    order = self.client.limit_buy(symbol, price=price, size=size)
                else:
                    order = self.client.limit_sell(symbol, price=price, size=size)
                orders.append(order)
                logger.info(f"Scale-in {symbol} {side} @ {price:.2f}, size={size:.6f}")
            except Exception as e:
                logger.error(f"Scale-in at {price} failed: {e}")

        return orders

    def dca(
        self,
        symbol: str,
        side: str,
        amount_usd: float,
        interval_seconds: float,
    ) -> threading.Thread:
        """
        Start a DCA (Dollar-Cost Averaging) schedule.

        Places a market order of amount_usd every interval_seconds
        in a background thread.

        Args:
            symbol: Token symbol.
            side: "BUY" or "SELL".
            amount_usd: USD amount per purchase.
            interval_seconds: Seconds between purchases.

        Returns:
            The background daemon thread. Call thread.join() to wait,
            or let it run indefinitely.

        Example:
            # DCA $100 into ETH every hour
            thread = agent.dca("ETH", "BUY", amount_usd=100, interval_seconds=3600)
            # To stop: set agent._halted = True or call agent._halt("manual")
        """
        self.risk_check(symbol, amount_usd)

        def _run():
            count = 0
            while not self._halted:
                try:
                    self.risk_check(symbol, amount_usd)
                    if side.upper() == "BUY":
                        order = self.client.buy(symbol, usd=amount_usd)
                    else:
                        order = self.client.sell(symbol, usd=amount_usd)
                    count += 1
                    self._emit("fill", {
                        "strategy": "dca",
                        "count": count,
                        "order": order,
                    })
                    logger.info(f"DCA {symbol} #{count}: ${amount_usd:.0f}")
                except ArthurError as e:
                    logger.error(f"DCA {symbol} #{count + 1} failed: {e}")
                    if self._halted:
                        break

                time.sleep(interval_seconds)

        t = threading.Thread(target=_run, daemon=True, name=f"dca-{symbol}")
        t.start()
        with self._lock:
            self._active_threads.append(t)
        return t

    # ==================== Convenience ====================

    def status(self) -> Dict[str, Any]:
        """
        Get full agent status and portfolio snapshot.

        Returns:
            Dict with agent state, risk info, and portfolio snapshot.
        """
        snapshot = self.portfolio.snapshot()
        current_equity = snapshot["equity"]

        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - current_equity) / self._peak_equity

        active_threads = []
        with self._lock:
            self._active_threads = [t for t in self._active_threads if t.is_alive()]
            active_threads = [t.name for t in self._active_threads]

        return {
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            "initial_equity": self._initial_equity,
            "peak_equity": self._peak_equity,
            "current_equity": current_equity,
            "current_drawdown": drawdown,
            "max_drawdown_limit": self.max_drawdown,
            "max_position_usd": self.max_position_usd,
            "active_strategies": active_threads,
            "portfolio": snapshot,
        }

    def __repr__(self) -> str:
        status = "HALTED" if self._halted else "ACTIVE"
        return (
            f"Agent(status={status}, max_dd={self.max_drawdown:.0%}, "
            f"max_pos=${self.max_position_usd:.0f})"
        )
