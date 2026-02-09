"""
Market Maker Strategy Runner for Orderly Network.

Enhanced market making with:
- Spread capture with inventory skew
- Funding rate awareness (bias towards paid side)
- Volatility-adjusted spreads
- Risk controls (stop loss, daily limits)
"""

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("arthur_sdk")

from .client import Arthur, Order, Position
from .exceptions import ArthurError, OrderError


@dataclass
class MMConfig:
    """Market maker configuration with funding and volatility support"""
    name: str
    symbol: str
    
    # Spread settings
    base_spread_bps: float = 25
    min_spread_bps: float = 18
    max_spread_bps: float = 80
    
    # Size settings
    order_size_usd: float = 50
    max_inventory_usd: float = 200
    levels: int = 1
    
    # Skew settings
    skew_per_100_usd: float = 8
    
    # Funding settings
    funding_enabled: bool = True
    funding_bias_threshold_pct: float = 0.03  # Min funding to apply bias
    funding_bias_bps: float = 3  # BPS to bias towards paid side
    
    # Volatility settings
    volatility_enabled: bool = True
    volatility_lookback_min: int = 5
    volatility_threshold_pct: float = 1.5
    volatility_spread_multiplier: float = 1.8
    volatility_pause_threshold_pct: float = 3.0
    
    # Risk settings
    max_position_usd: float = 300
    stop_loss_pct: float = 3
    take_profit_pct: float = 2
    daily_loss_limit_usd: float = 25
    max_drawdown_pct: float = 5
    
    # Execution
    post_only: bool = True
    requote_interval_sec: float = 30
    min_edge_bps: float = 5
    
    # Flags
    dry_run: bool = True
    log_quotes: bool = True
    
    @classmethod
    def from_file(cls, path: str) -> "MMConfig":
        """Load config from JSON file"""
        with open(Path(path).expanduser()) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MMConfig":
        """Create config from dict"""
        mm = data.get("market_making", {})
        funding = data.get("funding", {})
        vol = data.get("volatility", {})
        risk = data.get("risk", {})
        exec_cfg = data.get("execution", {})
        flags = data.get("flags", {})
        
        return cls(
            name=data.get("name", "Unnamed MM"),
            symbol=data.get("symbol", "ORDER"),
            # Spread
            base_spread_bps=mm.get("base_spread_bps", 25),
            min_spread_bps=mm.get("min_spread_bps", 18),
            max_spread_bps=mm.get("max_spread_bps", 80),
            # Size
            order_size_usd=mm.get("order_size_usd", 50),
            max_inventory_usd=mm.get("max_inventory_usd", 200),
            levels=mm.get("levels", 1),
            skew_per_100_usd=mm.get("skew_per_100_usd", 8),
            # Funding
            funding_enabled=funding.get("enabled", True),
            funding_bias_threshold_pct=funding.get("bias_threshold_pct", 0.03),
            funding_bias_bps=funding.get("bias_bps", 3),
            # Volatility
            volatility_enabled=vol.get("enabled", True),
            volatility_lookback_min=vol.get("lookback_minutes", 5),
            volatility_threshold_pct=vol.get("threshold_pct", 1.5),
            volatility_spread_multiplier=vol.get("spread_multiplier", 1.8),
            volatility_pause_threshold_pct=vol.get("pause_threshold_pct", 3.0),
            # Risk
            max_position_usd=risk.get("max_position_usd", 300),
            stop_loss_pct=risk.get("stop_loss_pct", 3),
            take_profit_pct=risk.get("take_profit_pct", 2),
            daily_loss_limit_usd=risk.get("daily_loss_limit_usd", 25),
            max_drawdown_pct=risk.get("max_drawdown_pct", 5),
            # Execution
            post_only=exec_cfg.get("post_only", True),
            requote_interval_sec=mm.get("requote_interval_sec", 30),
            min_edge_bps=exec_cfg.get("min_edge_bps", 5),
            # Flags
            dry_run=flags.get("dry_run", True),
            log_quotes=flags.get("log_quotes", True),
        )


class MarketMaker:
    """
    Enhanced market maker for Orderly Network.
    
    Features:
    1. Spread capture with inventory-based skew
    2. Funding rate awareness - bias towards paid side
    3. Volatility-adjusted spreads
    4. Risk controls (position limits, stop loss)
    
    Strategy Logic:
    - Base spread captures edge (e.g., 25 bps)
    - Inventory skew pushes quotes away from heavy side
    - Funding bias: if funding positive, favor shorts (get paid)
    - Volatility: widen spreads during high vol, pause during extreme
    
    Example:
        client = Arthur.from_credentials_file("creds.json")
        config = MMConfig.from_file("strategies/order-mm.json")
        mm = MarketMaker(client, config)
        mm.run_loop()
    """
    
    def __init__(self, client: Arthur, config: MMConfig):
        self.client = client
        self.config = config
        self.symbol = client._normalize_symbol(config.symbol)
        
        # State
        self.active_orders: Dict[str, Order] = {}
        self.last_quote_time: float = 0
        self.session_start: float = time.time()
        self.session_pnl: float = 0
        self.peak_equity: float = 0
        
        # Caches
        self._funding_rate: float = 0
        self._funding_cache_time: float = 0
        self._price_history: List[float] = []
        self._price_history_times: List[float] = []
    
    def get_funding_rate(self) -> float:
        """
        Get current funding rate for the symbol.
        
        Returns:
            Funding rate as decimal (e.g., 0.0005 = 0.05%)
            Positive = longs pay shorts
            Negative = shorts pay longs
        """
        # Cache for 5 minutes
        if time.time() - self._funding_cache_time < 300:
            return self._funding_rate
        
        try:
            url = f"https://api-evm.orderly.org/v1/public/futures/{self.symbol}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            
            if data.get("success"):
                rate = float(data["data"].get("est_funding_rate", 0))
                self._funding_rate = rate
                self._funding_cache_time = time.time()
                return rate
        except Exception as e:
            logger.warning(f"Failed to get funding rate: {e}")
        
        return self._funding_rate  # Return cached or 0
    
    def get_recent_volatility(self, mid_price: float) -> float:
        """
        Calculate recent price volatility as percentage.
        
        Returns:
            Volatility as percentage (e.g., 1.5 = 1.5% move)
        """
        now = time.time()
        lookback_sec = self.config.volatility_lookback_min * 60
        
        # Add current price
        self._price_history.append(mid_price)
        self._price_history_times.append(now)
        
        # Prune old prices
        cutoff = now - lookback_sec
        while self._price_history_times and self._price_history_times[0] < cutoff:
            self._price_history.pop(0)
            self._price_history_times.pop(0)
        
        if len(self._price_history) < 2:
            return 0
        
        # Calculate range volatility
        high = max(self._price_history)
        low = min(self._price_history)
        mid = (high + low) / 2
        
        if mid == 0:
            return 0
        
        return ((high - low) / mid) * 100
    
    def run_once(self) -> Dict[str, Any]:
        """
        Run one quote cycle.
        
        Returns:
            Dict with quote details and status
        """
        result = {
            "timestamp": int(time.time() * 1000),
            "symbol": self.symbol,
            "dry_run": self.config.dry_run,
        }
        
        try:
            # 1. Get market data
            spread_info = self.client.spread(self.config.symbol)
            mid_price = spread_info["mid"]
            market_spread_bps = spread_info["spread_bps"]
            
            result["mid_price"] = mid_price
            result["market_spread_bps"] = market_spread_bps
            
            # 2. Get funding rate
            funding_rate = self.get_funding_rate() if self.config.funding_enabled else 0
            result["funding_rate"] = funding_rate
            result["funding_apr"] = funding_rate * 3 * 365 * 100  # Annualized %
            
            # 3. Calculate volatility
            volatility = self.get_recent_volatility(mid_price) if self.config.volatility_enabled else 0
            result["volatility_pct"] = volatility
            
            # 4. Check for volatility pause
            if volatility >= self.config.volatility_pause_threshold_pct:
                result["status"] = "volatility_pause"
                result["action"] = "cancel_all"
                if not self.config.dry_run:
                    self.client.cancel_all(self.symbol)
                return result
            
            # 5. Get current position
            position = self.client.position(self.config.symbol)
            inventory_usd = 0
            position_pnl_pct = 0
            if position:
                inventory_usd = position.size * mid_price
                if position.side == "SHORT":
                    inventory_usd = -inventory_usd
                position_pnl_pct = position.pnl_percent
            
            result["inventory_usd"] = inventory_usd
            result["position_pnl_pct"] = position_pnl_pct
            
            # 6. Check risk limits
            # Max position
            if abs(inventory_usd) >= self.config.max_position_usd:
                result["status"] = "max_position"
                result["action"] = "cancel_all"
                if not self.config.dry_run:
                    self.client.cancel_all(self.symbol)
                return result
            
            # Stop loss
            if position and position_pnl_pct <= -self.config.stop_loss_pct:
                result["status"] = "stop_loss"
                result["action"] = "close_position"
                if not self.config.dry_run:
                    self.client.cancel_all(self.symbol)
                    self.client.close(self.config.symbol)
                return result
            
            # Take profit
            if position and position_pnl_pct >= self.config.take_profit_pct:
                result["status"] = "take_profit"
                result["action"] = "close_position"
                if not self.config.dry_run:
                    self.client.cancel_all(self.symbol)
                    self.client.close(self.config.symbol)
                return result
            
            # 7. Calculate quotes with all adjustments
            quotes = self._calculate_quotes(
                mid_price=mid_price,
                inventory_usd=inventory_usd,
                funding_rate=funding_rate,
                volatility=volatility,
            )
            result["quotes"] = quotes
            
            # 8. Place orders
            if self.config.dry_run:
                result["status"] = "dry_run"
                result["action"] = "would_quote"
            else:
                # Cancel existing orders
                self.client.cancel_all(self.symbol)
                
                # Place new quotes
                orders = self.client.quote(
                    symbol=self.config.symbol,
                    bid_price=quotes["bid_price"],
                    ask_price=quotes["ask_price"],
                    size=quotes["size"],
                    cancel_existing=False,
                )
                
                result["orders"] = {
                    "bid": orders["bid"].order_id,
                    "ask": orders["ask"].order_id,
                }
                result["status"] = "quoted"
                result["action"] = "placed_orders"
            
            self.last_quote_time = time.time()
            
            if self.config.log_quotes:
                self._log_quote(result)
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    def _calculate_quotes(
        self,
        mid_price: float,
        inventory_usd: float,
        funding_rate: float,
        volatility: float,
    ) -> Dict:
        """
        Calculate bid and ask prices with all adjustments.
        
        Adjustments applied:
        1. Base spread
        2. Inventory skew (push away from heavy side)
        3. Funding bias (favor paid side)
        4. Volatility adjustment (widen during high vol)
        """
        
        # 1. Base spread
        spread_bps = self.config.base_spread_bps
        
        # 2. Volatility adjustment
        if volatility > self.config.volatility_threshold_pct:
            vol_multiplier = min(
                self.config.volatility_spread_multiplier,
                1 + (volatility - self.config.volatility_threshold_pct) * 0.5
            )
            spread_bps *= vol_multiplier
        
        # Clamp spread
        spread_bps = max(self.config.min_spread_bps, min(self.config.max_spread_bps, spread_bps))
        
        # 3. Inventory skew: push away from heavy side
        # Positive inventory = long heavy = lower bids, higher asks (encourage sells)
        inventory_skew_bps = (inventory_usd / 100) * self.config.skew_per_100_usd
        
        # 4. Funding bias: favor the side that gets paid
        # Positive funding = longs pay shorts = favor shorts = negative bias
        funding_bias_bps = 0
        if abs(funding_rate * 100) >= self.config.funding_bias_threshold_pct:
            if funding_rate > 0:
                # Longs pay shorts - we want to be short
                # Negative bias = lower both bid and ask (encourage shorts)
                funding_bias_bps = -self.config.funding_bias_bps
            else:
                # Shorts pay longs - we want to be long
                # Positive bias = raise both bid and ask (encourage longs)
                funding_bias_bps = self.config.funding_bias_bps
        
        # Calculate prices
        half_spread = (spread_bps / 10000) * mid_price / 2
        inventory_skew_amount = (inventory_skew_bps / 10000) * mid_price
        funding_bias_amount = (funding_bias_bps / 10000) * mid_price
        
        # Apply all adjustments
        # Inventory skew shifts both quotes in same direction (away from inventory)
        # Funding bias also shifts both quotes
        bid_price = mid_price - half_spread - inventory_skew_amount + funding_bias_amount
        ask_price = mid_price + half_spread - inventory_skew_amount + funding_bias_amount
        
        # Ensure minimum spread
        min_spread = (self.config.min_spread_bps / 10000) * mid_price
        if ask_price - bid_price < min_spread:
            gap = min_spread - (ask_price - bid_price)
            bid_price -= gap / 2
            ask_price += gap / 2
        
        # Calculate size
        size = self.config.order_size_usd / mid_price
        
        # Round to tick size (ORDER has base_tick=1)
        size = max(1, round(size))
        
        # Round prices to quote tick (0.00001)
        bid_price = round(bid_price, 5)
        ask_price = round(ask_price, 5)
        
        return {
            "bid_price": bid_price,
            "ask_price": ask_price,
            "size": size,
            "spread_bps": ((ask_price - bid_price) / mid_price) * 10000,
            "inventory_skew_bps": inventory_skew_bps,
            "funding_bias_bps": funding_bias_bps,
            "volatility_adjusted": volatility > self.config.volatility_threshold_pct,
        }
    
    def _log_quote(self, result: Dict):
        """Log quote details"""
        quotes = result.get("quotes", {})
        mode = "[DRY]" if self.config.dry_run else "[LIVE]"
        
        funding_str = ""
        if result.get("funding_rate", 0) != 0:
            funding_apr = result.get("funding_apr", 0)
            bias = quotes.get("funding_bias_bps", 0)
            funding_str = f" | fund={funding_apr:.0f}%APR({bias:+.0f}bps)"
        
        vol_str = ""
        if quotes.get("volatility_adjusted"):
            vol_str = f" | vol={result.get('volatility_pct', 0):.1f}%⚠️"
        
        logger.info(f"{mode} {self.config.symbol} | "
                    f"mid=${result.get('mid_price', 0):.5f} | "
                    f"bid=${quotes.get('bid_price', 0):.5f} / "
                    f"ask=${quotes.get('ask_price', 0):.5f} | "
                    f"spread={quotes.get('spread_bps', 0):.0f}bps | "
                    f"inv=${result.get('inventory_usd', 0):+.0f}"
                    f"{funding_str}{vol_str}")
    
    def run_loop(self, duration_sec: Optional[float] = None):
        """
        Run continuous quoting loop.
        
        Args:
            duration_sec: Run for this many seconds (None = forever)
        """
        logger.info("=" * 60)
        logger.info(f"ORDER Market Maker - {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.config.symbol}")
        logger.info(f"Spread: {self.config.base_spread_bps} bps "
                    f"(min: {self.config.min_spread_bps}, max: {self.config.max_spread_bps})")
        logger.info(f"Size: ${self.config.order_size_usd} | "
                    f"Max Inventory: ${self.config.max_inventory_usd}")
        logger.info(f"Funding: {'ON' if self.config.funding_enabled else 'OFF'} | "
                    f"Volatility: {'ON' if self.config.volatility_enabled else 'OFF'}")
        logger.info(f"Mode: {'DRY RUN' if self.config.dry_run else 'LIVE'}")
        logger.info("=" * 60)
        
        start_time = time.time()
        cycles = 0
        
        try:
            while True:
                result = self.run_once()
                cycles += 1
                
                # Check duration
                if duration_sec and (time.time() - start_time) >= duration_sec:
                    break
                
                time.sleep(self.config.requote_interval_sec)
                
        except KeyboardInterrupt:
            logger.info("Stopping market maker...")
        finally:
            # Cancel all orders on exit
            if not self.config.dry_run:
                logger.info("Cancelling all orders...")
                try:
                    self.client.cancel_all(self.symbol)
                except Exception as e:
                    logger.warning(f"Failed to cancel orders on exit: {e}")
        
        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"Session complete: {cycles} cycles in {elapsed:.0f}s")
        logger.info("=" * 60)
    
    def status(self) -> Dict:
        """Get current MM status"""
        position = self.client.position(self.config.symbol)
        orders = self.client.orders(self.config.symbol)
        spread = self.client.spread(self.config.symbol)
        funding = self.get_funding_rate()
        
        return {
            "symbol": self.config.symbol,
            "mode": "dry_run" if self.config.dry_run else "live",
            "mid_price": spread["mid"],
            "market_spread_bps": spread["spread_bps"],
            "funding_rate": funding,
            "funding_apr": funding * 3 * 365 * 100,
            "position": {
                "side": position.side if position else None,
                "size": position.size if position else 0,
                "notional": position.size * spread["mid"] if position else 0,
                "pnl": position.unrealized_pnl if position else 0,
                "pnl_pct": position.pnl_percent if position else 0,
            },
            "open_orders": len(orders),
            "uptime_sec": time.time() - self.session_start,
        }


def run_mm(config_path: str, credentials_path: str, duration: Optional[float] = None):
    """
    Run market maker from config file.
    
    Args:
        config_path: Path to strategy JSON
        credentials_path: Path to credentials JSON
        duration: Run duration in seconds (None = forever)
    """
    client = Arthur.from_credentials_file(credentials_path)
    config = MMConfig.from_file(config_path)
    mm = MarketMaker(client, config)
    mm.run_loop(duration_sec=duration)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python -m arthur_sdk.market_maker <strategy.json> <credentials.json> [duration_sec]")
        sys.exit(1)
    
    strategy = sys.argv[1]
    creds = sys.argv[2]
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else None
    
    run_mm(strategy, creds, duration)
