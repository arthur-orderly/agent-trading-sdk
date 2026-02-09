"""
WebSocket-enabled Market Maker for Orderly Network.

Improvements over polling-based MM:
- Real-time fill notifications via WebSocket
- Immediate requote on fills (< 100ms)
- Periodic backup requotes (every 10s)
- Better inventory management
"""

import json
import logging
import time
import asyncio
import hashlib
import base64
import threading
import urllib.request
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
from pathlib import Path

logger = logging.getLogger("arthur_sdk")

# Import ed25519 for signing
try:
    from nacl.signing import SigningKey
    from nacl.encoding import Base64Encoder
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

from .client import Arthur, Order, Position
from .exceptions import ArthurError


@dataclass
class WSMMConfig:
    """WebSocket Market Maker configuration"""
    name: str
    symbol: str
    
    # Spread settings
    base_spread_bps: float = 25
    min_spread_bps: float = 18
    max_spread_bps: float = 80
    
    # Size settings
    order_size_usd: float = 50
    max_inventory_usd: float = 200
    
    # Skew settings
    skew_per_100_usd: float = 8
    
    # Funding settings
    funding_enabled: bool = True
    funding_bias_threshold_pct: float = 0.03
    funding_bias_bps: float = 3
    
    # Timing
    backup_requote_sec: float = 10  # Backup requote interval
    fill_requote_delay_ms: float = 50  # Delay after fill before requoting
    
    # Risk settings
    max_position_usd: float = 300
    stop_loss_pct: float = 3
    
    # Flags
    dry_run: bool = False
    log_quotes: bool = True
    log_fills: bool = True
    
    @classmethod
    def from_file(cls, path: str) -> "WSMMConfig":
        """Load config from JSON file"""
        with open(Path(path).expanduser()) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "WSMMConfig":
        """Create config from dict"""
        mm = data.get("market_making", {})
        funding = data.get("funding", {})
        risk = data.get("risk", {})
        flags = data.get("flags", {})
        
        return cls(
            name=data.get("name", "WS Market Maker"),
            symbol=data.get("symbol", "ORDER"),
            base_spread_bps=mm.get("base_spread_bps", 25),
            min_spread_bps=mm.get("min_spread_bps", 18),
            max_spread_bps=mm.get("max_spread_bps", 80),
            order_size_usd=mm.get("order_size_usd", 50),
            max_inventory_usd=mm.get("max_inventory_usd", 200),
            skew_per_100_usd=mm.get("skew_per_100_usd", 8),
            funding_enabled=funding.get("enabled", True),
            funding_bias_threshold_pct=funding.get("bias_threshold_pct", 0.03),
            funding_bias_bps=funding.get("bias_bps", 3),
            backup_requote_sec=mm.get("backup_requote_sec", mm.get("requote_interval_sec", 10)),
            max_position_usd=risk.get("max_position_usd", 300),
            stop_loss_pct=risk.get("stop_loss_pct", 3),
            dry_run=flags.get("dry_run", False),
            log_quotes=flags.get("log_quotes", True),
            log_fills=flags.get("log_fills", True),
        )


class WebSocketMarketMaker:
    """
    Event-driven market maker using WebSocket for real-time fills.
    
    Features:
    - Immediate requote on fill (< 100ms)
    - Backup timer requotes (every 10s)
    - Funding-aware quote skew
    - Inventory management
    
    Example:
        client = Arthur.from_credentials_file("creds.json")
        config = WSMMConfig.from_file("strategies/order-mm.json")
        mm = WebSocketMarketMaker(client, config, 
                                   orderly_key="ed25519:...",
                                   orderly_secret="ed25519:...")
        mm.run(duration_sec=3600)
    """
    
    WS_URL = "wss://ws-private-evm.orderly.org/v2/ws/private/stream"
    
    def __init__(
        self,
        client: Arthur,
        config: WSMMConfig,
        orderly_key: str,
        orderly_secret: str,
        account_id: str,
    ):
        self.client = client
        self.config = config
        self.symbol = client._normalize_symbol(config.symbol)
        self.orderly_key = orderly_key
        self.orderly_secret = orderly_secret
        self.account_id = account_id
        
        # State
        self.running = False
        self.ws_connected = False
        self.last_quote_time = 0
        self.last_fill_time = 0
        self.session_start = time.time()
        self.quote_count = 0
        self.fill_count = 0
        
        # Caches
        self._funding_rate = 0
        self._funding_cache_time = 0
        self._mid_price = 0
        self._inventory_usd = 0
        
        # Thread synchronization
        self._requote_lock = threading.Lock()
        self._pending_requote = False
    
    def _get_ws_signature(self, timestamp: int) -> str:
        """Generate WebSocket authentication signature"""
        from .auth import sign_message
        
        message = str(timestamp)
        return sign_message(self.orderly_secret, message)
    
    def get_funding_rate(self) -> float:
        """Get current funding rate (cached for 5 min)"""
        if time.time() - self._funding_cache_time < 300:
            return self._funding_rate
        
        try:
            url = f"https://api-evm.orderly.org/v1/public/futures/{self.symbol}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            
            if data.get("success"):
                self._funding_rate = float(data["data"].get("est_funding_rate", 0))
                self._funding_cache_time = time.time()
        except Exception as e:
            logger.warning(f"Failed to get funding rate: {e}")
        
        return self._funding_rate
    
    def calculate_quotes(self, mid_price: float, inventory_usd: float) -> Dict:
        """Calculate bid/ask prices with all adjustments"""
        # Base spread
        spread_bps = self.config.base_spread_bps
        
        # Inventory skew
        inventory_skew_bps = (inventory_usd / 100) * self.config.skew_per_100_usd
        
        # Funding bias
        funding_bias_bps = 0
        if self.config.funding_enabled:
            funding = self.get_funding_rate()
            if abs(funding * 100) >= self.config.funding_bias_threshold_pct:
                funding_bias_bps = -self.config.funding_bias_bps if funding > 0 else self.config.funding_bias_bps
        
        # Calculate prices
        half_spread = (spread_bps / 10000) * mid_price / 2
        inventory_skew = (inventory_skew_bps / 10000) * mid_price
        funding_bias = (funding_bias_bps / 10000) * mid_price
        
        bid_price = mid_price - half_spread - inventory_skew + funding_bias
        ask_price = mid_price + half_spread - inventory_skew + funding_bias
        
        # Ensure minimum spread
        min_spread = (self.config.min_spread_bps / 10000) * mid_price
        if ask_price - bid_price < min_spread:
            gap = min_spread - (ask_price - bid_price)
            bid_price -= gap / 2
            ask_price += gap / 2
        
        # Calculate size (ORDER has base_tick=1)
        size = max(1, round(self.config.order_size_usd / mid_price))
        
        # Round prices
        bid_price = round(bid_price, 5)
        ask_price = round(ask_price, 5)
        
        return {
            "bid_price": bid_price,
            "ask_price": ask_price,
            "size": size,
            "spread_bps": ((ask_price - bid_price) / mid_price) * 10000,
            "inventory_skew_bps": inventory_skew_bps,
            "funding_bias_bps": funding_bias_bps,
        }
    
    def requote(self, reason: str = "timer") -> Dict:
        """Cancel existing orders and place new quotes"""
        with self._requote_lock:
            result = {
                "timestamp": int(time.time() * 1000),
                "reason": reason,
            }
            
            try:
                # Get market data
                spread_info = self.client.spread(self.config.symbol)
                mid_price = spread_info["mid"]
                self._mid_price = mid_price
                
                # Get position
                position = self.client.position(self.config.symbol)
                inventory_usd = 0
                if position:
                    inventory_usd = position.size * mid_price
                    if position.side == "SHORT":
                        inventory_usd = -inventory_usd
                self._inventory_usd = inventory_usd
                
                result["mid_price"] = mid_price
                result["inventory_usd"] = inventory_usd
                
                # Check risk limits
                if abs(inventory_usd) >= self.config.max_position_usd:
                    result["status"] = "max_position"
                    if not self.config.dry_run:
                        self.client.cancel_all(self.symbol)
                    return result
                
                # Check stop loss
                if position and position.pnl_percent <= -self.config.stop_loss_pct:
                    result["status"] = "stop_loss"
                    if not self.config.dry_run:
                        self.client.cancel_all(self.symbol)
                        self.client.close(self.config.symbol)
                    return result
                
                # Calculate new quotes
                quotes = self.calculate_quotes(mid_price, inventory_usd)
                result["quotes"] = quotes
                
                # Place orders
                if self.config.dry_run:
                    result["status"] = "dry_run"
                else:
                    self.client.cancel_all(self.symbol)
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
                
                self.last_quote_time = time.time()
                self.quote_count += 1
                
                if self.config.log_quotes:
                    self._log_quote(result)
                
            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                logger.error(f"Requote error: {e}")
            
            return result
    
    def _log_quote(self, result: Dict):
        """Log quote details"""
        quotes = result.get("quotes", {})
        mode = "[DRY]" if self.config.dry_run else "[LIVE]"
        reason = result.get("reason", "?")[:5]
        
        funding_apr = self.get_funding_rate() * 3 * 365 * 100
        
        logger.info(f"{mode} {self.config.symbol} [{reason}] | "
                    f"mid=${result.get('mid_price', 0):.5f} | "
                    f"bid=${quotes.get('bid_price', 0):.5f} / "
                    f"ask=${quotes.get('ask_price', 0):.5f} | "
                    f"inv=${result.get('inventory_usd', 0):+.0f} | "
                    f"fund={funding_apr:.0f}%APR")
    
    def on_fill(self, data: Dict):
        """Handle fill event from WebSocket"""
        self.fill_count += 1
        self.last_fill_time = time.time()
        
        side = data.get("side", "?")
        qty = data.get("executedQuantity", data.get("quantity", 0))
        price = data.get("executedPrice", data.get("price", 0))
        
        if self.config.log_fills:
            logger.info(f"🔔 FILL: {side} {qty} @ ${price:.5f}")
        
        # Immediate requote after short delay
        time.sleep(self.config.fill_requote_delay_ms / 1000)
        self.requote(reason="fill")
    
    async def _ws_handler(self):
        """WebSocket connection handler"""
        ws_url = f"{self.WS_URL}/{self.account_id}"
        
        logger.info(f"Connecting to WebSocket: {ws_url[:50]}...")
        
        try:
            async with websockets.connect(ws_url) as ws:
                self.ws_connected = True
                logger.info("WebSocket connected")
                
                # Authenticate
                timestamp = int(time.time() * 1000)
                signature = self._get_ws_signature(timestamp)
                
                auth_msg = {
                    "id": "auth",
                    "event": "auth",
                    "params": {
                        "orderly_key": self.orderly_key,
                        "sign": signature,
                        "timestamp": timestamp,
                    }
                }
                await ws.send(json.dumps(auth_msg))
                
                # Wait for auth response
                auth_resp = await asyncio.wait_for(ws.recv(), timeout=10)
                auth_data = json.loads(auth_resp)
                
                if auth_data.get("event") == "auth" and auth_data.get("success"):
                    logger.info("WebSocket authenticated")
                else:
                    logger.error(f"WebSocket auth failed: {auth_data}")
                    return
                
                # Subscribe to execution reports
                sub_msg = {
                    "id": "sub_exec",
                    "event": "subscribe",
                    "topic": "executionreport",
                }
                await ws.send(json.dumps(sub_msg))
                logger.info("Subscribed to executionreport")
                
                # Listen for messages
                while self.running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)
                        
                        # Handle execution report
                        if data.get("topic") == "executionreport":
                            event_data = data.get("data", {})
                            status = event_data.get("status", "")
                            
                            if status in ["FILLED", "PARTIAL_FILLED"]:
                                # Run fill handler in separate thread to not block
                                threading.Thread(
                                    target=self.on_fill,
                                    args=(event_data,),
                                    daemon=True
                                ).start()
                        
                        # Handle pings
                        elif data.get("event") == "ping":
                            pong = {"event": "pong", "ts": data.get("ts")}
                            await ws.send(json.dumps(pong))
                    
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"WS message error: {e}")
                
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.ws_connected = False
            logger.info("WebSocket disconnected")
    
    def _backup_requote_loop(self):
        """Backup requote loop (runs in separate thread)"""
        while self.running:
            time.sleep(self.config.backup_requote_sec)
            
            # Only requote if no recent quote from fill handler
            if time.time() - self.last_quote_time >= self.config.backup_requote_sec * 0.8:
                self.requote(reason="timer")
    
    def run(self, duration_sec: Optional[float] = None):
        """
        Run the WebSocket market maker.
        
        Args:
            duration_sec: Run duration (None = forever)
        """
        if not HAS_WEBSOCKETS:
            raise ArthurError("websockets library required. Install with: pip install websockets")
        
        logger.info("=" * 60)
        logger.info(f"WebSocket Market Maker - {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.config.symbol}")
        logger.info(f"Spread: {self.config.base_spread_bps} bps")
        logger.info(f"Size: ${self.config.order_size_usd}")
        logger.info(f"Backup requote: {self.config.backup_requote_sec}s")
        logger.info(f"Mode: {'DRY RUN' if self.config.dry_run else 'LIVE'}")
        logger.info("=" * 60)
        
        self.running = True
        self.session_start = time.time()
        
        # Initial quote
        self.requote(reason="start")
        
        # Start backup requote thread
        backup_thread = threading.Thread(target=self._backup_requote_loop, daemon=True)
        backup_thread.start()
        
        # Run WebSocket in event loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def main():
                ws_task = asyncio.create_task(self._ws_handler())
                
                if duration_sec:
                    await asyncio.sleep(duration_sec)
                    self.running = False
                else:
                    while self.running:
                        await asyncio.sleep(1)
                
                ws_task.cancel()
            
            loop.run_until_complete(main())
            
        except KeyboardInterrupt:
            logger.info("Stopping WebSocket market maker...")
        finally:
            self.running = False
            
            # Cancel all orders
            if not self.config.dry_run:
                logger.info("Cancelling all orders...")
                try:
                    self.client.cancel_all(self.symbol)
                except Exception as e:
                    logger.warning(f"Failed to cancel orders on exit: {e}")
        
        # Log summary
        elapsed = time.time() - self.session_start
        logger.info("=" * 60)
        logger.info("SESSION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {elapsed/3600:.1f} hours")
        logger.info(f"Quotes: {self.quote_count}")
        logger.info(f"Fills: {self.fill_count}")
        logger.info(f"Balance: ${self.client.balance():.2f}")
        logger.info("=" * 60)


def run_ws_mm(config_path: str, credentials_path: str, duration_hours: float = None):
    """
    Run WebSocket market maker from config files.
    
    Args:
        config_path: Path to strategy JSON
        credentials_path: Path to credentials JSON
        duration_hours: Run duration in hours (None = forever)
    """
    # Load credentials
    with open(Path(credentials_path).expanduser()) as f:
        creds = json.load(f)
    
    client = Arthur(
        api_key=creds.get("orderly_key") or creds.get("key"),
        secret_key=creds.get("orderly_secret") or creds.get("secret_key"),
        account_id=creds.get("account_id"),
    )
    
    config = WSMMConfig.from_file(config_path)
    
    mm = WebSocketMarketMaker(
        client=client,
        config=config,
        orderly_key=creds.get("orderly_key") or creds.get("key"),
        orderly_secret=creds.get("orderly_secret") or creds.get("secret_key"),
        account_id=creds.get("account_id"),
    )
    
    duration_sec = duration_hours * 3600 if duration_hours else None
    mm.run(duration_sec=duration_sec)
