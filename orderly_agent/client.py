"""
Arthur SDK Client - Main trading interface for AI agents.
"""

import json
import time
import hmac
import hashlib
import base64
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass
import urllib.request
import urllib.error

from .exceptions import ArthurError, AuthError, OrderError, InsufficientFundsError
from .auth import generate_auth_headers


@dataclass
class Position:
    """Represents an open position"""
    symbol: str
    side: str  # "LONG" or "SHORT"
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float
    
    @property
    def pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0
        return (self.unrealized_pnl / (self.size * self.entry_price)) * 100


@dataclass 
class Order:
    """Represents an order"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: Optional[float]
    size: float
    status: str
    created_at: int


class Arthur:
    """
    Arthur SDK Client - Simple trading for AI agents.
    
    Example:
        client = Arthur(api_key="your_key", secret_key="your_secret")
        client.buy("ETH", usd=100)
        client.positions()
    """
    
    BASE_URL = "https://api-evm.orderly.org"
    BROKER_ID = "orderly"  # Will change to arthur_dex when registered
    
    # Symbol mappings for convenience
    SYMBOL_MAP = {
        "BTC": "PERP_BTC_USDC",
        "ETH": "PERP_ETH_USDC", 
        "SOL": "PERP_SOL_USDC",
        "ARB": "PERP_ARB_USDC",
        "OP": "PERP_OP_USDC",
        "AVAX": "PERP_AVAX_USDC",
        "LINK": "PERP_LINK_USDC",
        "DOGE": "PERP_DOGE_USDC",
        "SUI": "PERP_SUI_USDC",
        "TIA": "PERP_TIA_USDC",
        "WOO": "PERP_WOO_USDC",
        "ORDER": "PERP_ORDER_USDC",
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        account_id: Optional[str] = None,
        testnet: bool = False,
    ):
        """
        Initialize Arthur client.
        
        Args:
            api_key: Orderly API key (ed25519:xxx format)
            secret_key: Orderly secret key (ed25519:xxx format)
            account_id: Orderly account ID
            testnet: Use testnet instead of mainnet
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.account_id = account_id
        
        if testnet:
            self.BASE_URL = "https://testnet-api-evm.orderly.org"
            
        self._prices_cache = {}
        self._prices_cache_time = 0
        
    @classmethod
    def from_credentials_file(cls, path: str, testnet: bool = False) -> "Arthur":
        """
        Load credentials from a JSON file.
        
        Args:
            path: Path to credentials JSON file
            testnet: Use testnet
            
        Returns:
            Configured Arthur client
        """
        with open(path) as f:
            creds = json.load(f)
        
        return cls(
            api_key=creds.get("orderly_key") or creds.get("api_key") or creds.get("key"),
            secret_key=creds.get("orderly_secret") or creds.get("secret_key"),
            account_id=creds.get("account_id"),
            testnet=testnet,
        )
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Convert short symbol (ETH) to full symbol (PERP_ETH_USDC)"""
        symbol = symbol.upper()
        if symbol in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol]
        if symbol.startswith("PERP_"):
            return symbol
        return f"PERP_{symbol}_USDC"
    
    def _sign_request(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Generate signed headers for authenticated request"""
        if not self.api_key or not self.secret_key or not self.account_id:
            raise AuthError("Missing credentials: api_key, secret_key, and account_id required")
        
        return generate_auth_headers(
            api_key=self.api_key,
            secret_key=self.secret_key,
            account_id=self.account_id,
            method=method,
            path=path,
            body=body,
        )
    
    def _request(
        self, 
        method: str, 
        path: str, 
        data: Optional[Dict] = None,
        auth: bool = True
    ) -> Dict:
        """Make HTTP request to Orderly API"""
        url = f"{self.BASE_URL}{path}"
        body = json.dumps(data) if data else ""
        
        headers = {}
        if auth:
            headers = self._sign_request(method, path, body)
        else:
            headers = {"Content-Type": "application/json"}
        
        req = urllib.request.Request(
            url,
            data=body.encode() if body else None,
            headers=headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                error_data = json.loads(error_body)
                raise ArthurError(f"API Error: {error_data.get('message', error_body)}")
            except json.JSONDecodeError:
                raise ArthurError(f"API Error ({e.code}): {error_body}")
    
    # ==================== Market Data ====================
    
    def price(self, symbol: str) -> float:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Token symbol (e.g., "ETH" or "PERP_ETH_USDC")
            
        Returns:
            Current mark price
        """
        symbol = self._normalize_symbol(symbol)
        
        # Check cache (5 second TTL)
        now = time.time()
        if now - self._prices_cache_time < 5 and symbol in self._prices_cache:
            return self._prices_cache[symbol]
        
        resp = self._request("GET", f"/v1/public/futures/{symbol}", auth=False)
        if resp.get("success"):
            price = float(resp["data"]["mark_price"])
            self._prices_cache[symbol] = price
            self._prices_cache_time = now
            return price
        raise ArthurError(f"Failed to get price for {symbol}")
    
    def prices(self) -> Dict[str, float]:
        """Get prices for all supported symbols"""
        resp = self._request("GET", "/v1/public/futures", auth=False)
        if resp.get("success"):
            prices = {}
            for item in resp["data"]["rows"]:
                symbol = item["symbol"]
                prices[symbol] = float(item["mark_price"])
                # Also add short name
                short = symbol.replace("PERP_", "").replace("_USDC", "")
                prices[short] = float(item["mark_price"])
            self._prices_cache = prices
            self._prices_cache_time = time.time()
            return prices
        raise ArthurError("Failed to get prices")
    
    # ==================== Account ====================
    
    def balance(self) -> float:
        """
        Get available USDC balance.
        
        Returns:
            Available balance in USDC
        """
        resp = self._request("GET", "/v1/client/holding")
        if resp.get("success"):
            for holding in resp["data"]["holding"]:
                if holding["token"] == "USDC":
                    return float(holding["holding"])
        return 0.0
    
    def equity(self) -> float:
        """
        Get total account equity (balance + unrealized PnL).
        
        Returns:
            Total equity in USDC
        """
        resp = self._request("GET", "/v1/client/holding")
        if resp.get("success"):
            return float(resp["data"].get("total_equity", 0))
        return 0.0
    
    # ==================== Positions ====================
    
    def positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        resp = self._request("GET", "/v1/positions")
        if not resp.get("success"):
            return []
        
        positions = []
        for row in resp["data"].get("rows", []):
            if float(row.get("position_qty", 0)) != 0:
                positions.append(Position(
                    symbol=row["symbol"],
                    side="LONG" if float(row["position_qty"]) > 0 else "SHORT",
                    size=abs(float(row["position_qty"])),
                    entry_price=float(row.get("average_open_price", 0)),
                    mark_price=float(row.get("mark_price", 0)),
                    unrealized_pnl=float(row.get("unrealized_pnl", 0)),
                    leverage=float(row.get("leverage", 1)),
                ))
        return positions
    
    def position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Token symbol
            
        Returns:
            Position object or None if no position
        """
        symbol = self._normalize_symbol(symbol)
        for pos in self.positions():
            if pos.symbol == symbol:
                return pos
        return None
    
    def pnl(self) -> float:
        """
        Get total unrealized PnL across all positions.
        
        Returns:
            Total unrealized PnL in USDC
        """
        return sum(pos.unrealized_pnl for pos in self.positions())
    
    # ==================== Trading ====================
    
    def buy(
        self,
        symbol: str,
        size: Optional[float] = None,
        usd: Optional[float] = None,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Order:
        """
        Open or add to a long position.
        
        Args:
            symbol: Token symbol (e.g., "ETH")
            size: Position size in base asset (e.g., 0.1 ETH)
            usd: Position size in USD (alternative to size)
            price: Limit price (None for market order)
            reduce_only: Only reduce existing position
            
        Returns:
            Order object
            
        Example:
            client.buy("ETH", usd=100)  # Buy $100 worth of ETH
            client.buy("BTC", size=0.01)  # Buy 0.01 BTC
        """
        return self._place_order(
            symbol=symbol,
            side="BUY",
            size=size,
            usd=usd,
            price=price,
            reduce_only=reduce_only,
        )
    
    def sell(
        self,
        symbol: str,
        size: Optional[float] = None,
        usd: Optional[float] = None,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Order:
        """
        Open or add to a short position.
        
        Args:
            symbol: Token symbol
            size: Position size in base asset
            usd: Position size in USD
            price: Limit price (None for market order)
            reduce_only: Only reduce existing position
            
        Returns:
            Order object
        """
        return self._place_order(
            symbol=symbol,
            side="SELL",
            size=size,
            usd=usd,
            price=price,
            reduce_only=reduce_only,
        )
    
    def close(self, symbol: str, size: Optional[float] = None) -> Optional[Order]:
        """
        Close a position (partially or fully).
        
        Args:
            symbol: Token symbol
            size: Size to close (None = close entire position)
            
        Returns:
            Order object, or None if no position to close
        """
        pos = self.position(symbol)
        if not pos:
            return None
        
        close_size = size or pos.size
        close_side = "SELL" if pos.side == "LONG" else "BUY"
        
        return self._place_order(
            symbol=symbol,
            side=close_side,
            size=close_size,
            reduce_only=True,
        )
    
    def close_all(self) -> List[Order]:
        """
        Close all open positions.
        
        Returns:
            List of Order objects for each closed position
        """
        orders = []
        for pos in self.positions():
            order = self.close(pos.symbol)
            if order:
                orders.append(order)
        return orders
    
    def _place_order(
        self,
        symbol: str,
        side: str,
        size: Optional[float] = None,
        usd: Optional[float] = None,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Order:
        """Internal method to place an order"""
        symbol = self._normalize_symbol(symbol)
        
        # Calculate size from USD if needed
        if usd and not size:
            current_price = self.price(symbol)
            size = usd / current_price
        
        if not size:
            raise OrderError("Must specify either size or usd")
        
        order_type = "LIMIT" if price else "MARKET"
        
        order_data = {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "order_quantity": str(size),
            "reduce_only": reduce_only,
        }
        
        if price:
            order_data["order_price"] = str(price)
        
        resp = self._request("POST", "/v1/order", data=order_data)
        
        if not resp.get("success"):
            error = resp.get("message", "Unknown error")
            if "insufficient" in error.lower():
                raise InsufficientFundsError(error)
            raise OrderError(error)
        
        data = resp["data"]
        return Order(
            order_id=str(data["order_id"]),
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            size=size,
            status=data.get("status", "NEW"),
            created_at=int(time.time() * 1000),
        )
    
    # ==================== Risk Management ====================
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Token symbol
            leverage: Leverage multiplier (1-50)
            
        Returns:
            True if successful
        """
        symbol = self._normalize_symbol(symbol)
        resp = self._request(
            "POST",
            "/v1/client/leverage",
            data={"symbol": symbol, "leverage": leverage}
        )
        return resp.get("success", False)
    
    def set_stop_loss(
        self,
        symbol: str,
        price: Optional[float] = None,
        pct: Optional[float] = None,
    ) -> Order:
        """
        Set stop loss for a position.
        
        Args:
            symbol: Token symbol
            price: Stop price
            pct: Stop loss percentage from entry (alternative to price)
            
        Returns:
            Order object for stop loss
        """
        pos = self.position(symbol)
        if not pos:
            raise OrderError(f"No position for {symbol}")
        
        if pct and not price:
            if pos.side == "LONG":
                price = pos.entry_price * (1 - pct / 100)
            else:
                price = pos.entry_price * (1 + pct / 100)
        
        if not price:
            raise OrderError("Must specify price or pct")
        
        # Place stop loss order
        side = "SELL" if pos.side == "LONG" else "BUY"
        return self._place_order(
            symbol=symbol,
            side=side,
            size=pos.size,
            price=price,
            reduce_only=True,
        )
    
    # ==================== Info ====================
    
    def orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get open orders.
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of Order objects
        """
        path = "/v1/orders"
        if symbol:
            path += f"?symbol={self._normalize_symbol(symbol)}"
        
        resp = self._request("GET", path)
        if not resp.get("success"):
            return []
        
        orders = []
        for row in resp["data"].get("rows", []):
            orders.append(Order(
                order_id=str(row["order_id"]),
                symbol=row["symbol"],
                side=row["side"],
                order_type=row["type"],
                price=float(row.get("price")) if row.get("price") else None,
                size=float(row["quantity"]),
                status=row["status"],
                created_at=int(row["created_time"]),
            ))
        return orders
    
    def cancel(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Symbol of the order
            
        Returns:
            True if cancelled successfully
        """
        symbol = self._normalize_symbol(symbol)
        resp = self._request(
            "DELETE",
            f"/v1/order?order_id={order_id}&symbol={symbol}"
        )
        return resp.get("success", False)
    
    def cancel_all(self, symbol: Optional[str] = None) -> int:
        """
        Cancel all open orders.
        
        Args:
            symbol: Cancel only orders for this symbol (optional)
            
        Returns:
            Number of orders cancelled
        """
        path = "/v1/orders"
        if symbol:
            path += f"?symbol={self._normalize_symbol(symbol)}"
        
        resp = self._request("DELETE", path)
        if resp.get("success"):
            return resp["data"].get("cancelled_count", 0)
        return 0
    
    # ==================== Convenience ====================
    
    def summary(self) -> Dict[str, Any]:
        """
        Get account summary including balance, positions, and PnL.
        
        Returns:
            Dict with account summary
        """
        positions = self.positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        
        return {
            "balance": self.balance(),
            "equity": self.equity(),
            "positions": len(positions),
            "unrealized_pnl": total_pnl,
            "position_details": [
                {
                    "symbol": p.symbol.replace("PERP_", "").replace("_USDC", ""),
                    "side": p.side,
                    "size": p.size,
                    "entry": p.entry_price,
                    "mark": p.mark_price,
                    "pnl": p.unrealized_pnl,
                    "pnl_pct": p.pnl_percent,
                }
                for p in positions
            ]
        }
    
    def __repr__(self) -> str:
        return f"Arthur(account_id={self.account_id[:8]}...)" if self.account_id else "Arthur(not authenticated)"
