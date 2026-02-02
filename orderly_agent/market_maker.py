"""
Market Maker Strategy Runner for Orderly Network.

Simple market making: place limit orders on both sides, manage inventory,
capture spread.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path

from .client import Arthur, Order, Position
from .exceptions import ArthurError, OrderError


@dataclass
class MMConfig:
    """Market maker configuration"""
    name: str
    symbol: str
    
    # Spread settings
    base_spread_bps: float = 30  # Base spread in basis points
    min_spread_bps: float = 15   # Minimum spread
    
    # Size settings
    order_size_usd: float = 50   # Size per side in USD
    max_inventory_usd: float = 300  # Max inventory before skewing
    levels: int = 1              # Number of price levels
    
    # Skew settings
    skew_per_100_usd: float = 5  # BPS to skew per $100 inventory
    
    # Risk settings
    max_position_usd: float = 500
    stop_loss_pct: float = 5
    daily_loss_limit_usd: float = 50
    
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
        
        mm = data.get("market_making", {})
        risk = data.get("risk", {})
        exec_cfg = data.get("execution", {})
        flags = data.get("flags", {})
        
        return cls(
            name=data.get("name", "Unnamed MM"),
            symbol=data.get("symbol", "ORDER"),
            base_spread_bps=mm.get("base_spread_bps", 30),
            min_spread_bps=mm.get("min_spread_bps", 15),
            order_size_usd=mm.get("order_size_usd", 50),
            max_inventory_usd=mm.get("max_inventory_usd", 300),
            levels=mm.get("levels", 1),
            skew_per_100_usd=mm.get("skew_per_100_usd", 5),
            max_position_usd=risk.get("max_position_usd", 500),
            stop_loss_pct=risk.get("stop_loss_pct", 5),
            daily_loss_limit_usd=risk.get("daily_loss_limit_usd", 50),
            post_only=exec_cfg.get("post_only", True),
            requote_interval_sec=mm.get("requote_interval_sec", 30),
            min_edge_bps=exec_cfg.get("min_edge_bps", 5),
            dry_run=flags.get("dry_run", True),
            log_quotes=flags.get("log_quotes", True),
        )


class MarketMaker:
    """
    Simple market maker for Orderly Network.
    
    Strategy:
    1. Get mid price from orderbook
    2. Calculate bid/ask prices based on spread
    3. Skew quotes based on inventory
    4. Place/update limit orders
    5. Repeat every N seconds
    
    Example:
        client = Arthur.from_credentials_file("creds.json")
        mm = MarketMaker(client, MMConfig.from_file("strategies/order-mm.json"))
        mm.run_once()  # Single quote cycle
        mm.run_loop()  # Continuous quoting
    """
    
    def __init__(self, client: Arthur, config: MMConfig):
        self.client = client
        self.config = config
        self.symbol = client._normalize_symbol(config.symbol)
        
        # State
        self.active_orders: Dict[str, Order] = {}  # order_id -> Order
        self.last_quote_time: float = 0
        self.daily_pnl: float = 0
        self.session_start: float = time.time()
        
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
            
            # 2. Get current position
            position = self.client.position(self.config.symbol)
            inventory_usd = 0
            if position:
                inventory_usd = position.size * mid_price
                if position.side == "SHORT":
                    inventory_usd = -inventory_usd
            
            result["inventory_usd"] = inventory_usd
            
            # 3. Check risk limits
            if abs(inventory_usd) >= self.config.max_position_usd:
                result["status"] = "max_inventory"
                result["action"] = "cancel_all"
                if not self.config.dry_run:
                    self.client.cancel_all(self.symbol)
                return result
            
            # 4. Calculate quotes
            quotes = self._calculate_quotes(mid_price, inventory_usd)
            result["quotes"] = quotes
            
            # 5. Place orders
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
                    cancel_existing=False,  # Already cancelled
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
    
    def _calculate_quotes(self, mid_price: float, inventory_usd: float) -> Dict:
        """Calculate bid and ask prices based on config and inventory"""
        
        # Base spread
        spread_bps = self.config.base_spread_bps
        
        # Inventory skew: widen on the side we're heavy
        skew_bps = (inventory_usd / 100) * self.config.skew_per_100_usd
        
        # Calculate prices
        half_spread = (spread_bps / 10000) * mid_price / 2
        skew_amount = (skew_bps / 10000) * mid_price
        
        bid_price = mid_price - half_spread - skew_amount
        ask_price = mid_price + half_spread - skew_amount
        
        # Ensure minimum spread
        min_spread = (self.config.min_spread_bps / 10000) * mid_price
        if ask_price - bid_price < min_spread:
            # Widen symmetrically
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
            "skew_bps": skew_bps,
        }
    
    def _log_quote(self, result: Dict):
        """Log quote details"""
        quotes = result.get("quotes", {})
        mode = "[DRY]" if self.config.dry_run else "[LIVE]"
        
        print(f"{mode} {self.config.symbol} | "
              f"mid=${result.get('mid_price', 0):.5f} | "
              f"bid=${quotes.get('bid_price', 0):.5f} / "
              f"ask=${quotes.get('ask_price', 0):.5f} | "
              f"spread={quotes.get('spread_bps', 0):.1f}bps | "
              f"inv=${result.get('inventory_usd', 0):.0f}")
    
    def run_loop(self, duration_sec: Optional[float] = None):
        """
        Run continuous quoting loop.
        
        Args:
            duration_sec: Run for this many seconds (None = forever)
        """
        print(f"Starting market maker for {self.config.symbol}")
        print(f"Spread: {self.config.base_spread_bps}bps | "
              f"Size: ${self.config.order_size_usd} | "
              f"Interval: {self.config.requote_interval_sec}s")
        print(f"Mode: {'DRY RUN' if self.config.dry_run else 'LIVE'}")
        print("-" * 60)
        
        start_time = time.time()
        
        try:
            while True:
                self.run_once()
                
                # Check duration
                if duration_sec and (time.time() - start_time) >= duration_sec:
                    break
                
                time.sleep(self.config.requote_interval_sec)
                
        except KeyboardInterrupt:
            print("\nStopping market maker...")
        finally:
            # Cancel all orders on exit
            if not self.config.dry_run:
                print("Cancelling all orders...")
                self.client.cancel_all(self.symbol)
        
        print("Market maker stopped.")
    
    def status(self) -> Dict:
        """Get current MM status"""
        position = self.client.position(self.config.symbol)
        orders = self.client.orders(self.config.symbol)
        spread = self.client.spread(self.config.symbol)
        
        return {
            "symbol": self.config.symbol,
            "mode": "dry_run" if self.config.dry_run else "live",
            "mid_price": spread["mid"],
            "market_spread_bps": spread["spread_bps"],
            "position": {
                "side": position.side if position else None,
                "size": position.size if position else 0,
                "pnl": position.unrealized_pnl if position else 0,
            } if position else None,
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
        print("Usage: python -m orderly_agent.market_maker <strategy.json> <credentials.json> [duration_sec]")
        sys.exit(1)
    
    strategy = sys.argv[1]
    creds = sys.argv[2]
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else None
    
    run_mm(strategy, creds, duration)
