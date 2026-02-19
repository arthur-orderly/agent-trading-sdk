"""
Shared Orderly client for AI agent integrations.
Uses the existing auth module for proper ED25519 signing.
"""

import os
import json
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

try:
    import httpx
except ImportError:
    raise ImportError("httpx is required. Install with: pip install httpx")

from ..auth import generate_auth_headers


@dataclass
class OrderlyConfig:
    """Configuration for Orderly API client."""
    account_id: str
    api_key: str       # ed25519:xxx format (public key)
    secret_key: str    # ed25519:xxx format (private key for signing)
    api_base: str = "https://api-evm.orderly.org"
    
    @classmethod
    def from_env(cls) -> 'OrderlyConfig':
        """Load configuration from environment variables."""
        account_id = os.getenv("ORDERLY_ACCOUNT_ID")
        api_key = os.getenv("ORDERLY_API_KEY")
        secret_key = os.getenv("ORDERLY_SECRET_KEY") or os.getenv("ORDERLY_PRIVATE_KEY")
        api_base = os.getenv("ORDERLY_API_BASE", "https://api-evm.orderly.org")
        
        if not account_id:
            raise ValueError(
                "ORDERLY_ACCOUNT_ID is required. Get it from https://orderly.network\n"
                "Set it with: export ORDERLY_ACCOUNT_ID='0x...'"
            )
        if not api_key:
            raise ValueError(
                "ORDERLY_API_KEY is required (ed25519:xxx format).\n"
                "Generate one at https://orderly.network or via the SDK.\n"
                "Set it with: export ORDERLY_API_KEY='ed25519:...'"
            )
        if not secret_key:
            raise ValueError(
                "ORDERLY_SECRET_KEY is required (ed25519:xxx format).\n"
                "Set it with: export ORDERLY_SECRET_KEY='ed25519:...'"
            )
            
        return cls(account_id=account_id, api_key=api_key, secret_key=secret_key, api_base=api_base)


class OrderlyClient:
    """Lightweight client for Orderly Network API."""
    
    def __init__(self, config: Optional[OrderlyConfig] = None):
        self.config = config or OrderlyConfig.from_env()
        self._client = httpx.Client(base_url=self.config.api_base, timeout=15.0)
        
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        authenticated: bool = True
    ) -> Dict[str, Any]:
        """Make HTTP request to Orderly API."""
        path = endpoint if endpoint.startswith('/') else f'/{endpoint}'
        body = json.dumps(data) if data else ""
        
        headers = {"Content-Type": "application/json"}
        
        if authenticated:
            headers = generate_auth_headers(
                api_key=self.config.api_key,
                secret_key=self.config.secret_key,
                account_id=self.config.account_id,
                method=method.upper(),
                path=path,
                body=body,
            )
        
        try:
            if method.upper() == "GET":
                response = self._client.get(path, headers=headers)
            elif method.upper() == "POST":
                response = self._client.post(path, headers=headers, content=body)
            elif method.upper() == "DELETE":
                response = self._client.delete(path, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                detail = error_data.get("message", str(e))
            except Exception:
                detail = e.response.text or str(e)
            raise Exception(f"Orderly API error ({e.response.status_code}): {detail}")
        except httpx.ConnectError:
            raise Exception(f"Cannot connect to Orderly API at {self.config.api_base}. Check your network.")
        except Exception as e:
            if "Orderly API" in str(e):
                raise
            raise Exception(f"Request failed: {e}")
    
    # ── Public endpoints ──
    
    def get_futures_info(self) -> List[Dict[str, Any]]:
        """Get all available futures symbols with trading rules."""
        resp = self._request("GET", "/v1/public/futures", authenticated=False)
        return resp.get("data", {}).get("rows", [])
    
    def get_market_trades(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent trades for a symbol."""
        resp = self._request("GET", f"/v1/public/market_trades?symbol={symbol}&limit={limit}", authenticated=False)
        return resp.get("data", {}).get("rows", [])
    
    def get_orderbook(self, symbol: str, max_level: int = 10) -> Dict[str, Any]:
        """Get L2 orderbook data."""
        resp = self._request("GET", f"/v1/orderbook/{symbol}?max_level={max_level}")
        return resp.get("data", {})
    
    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get predicted funding rate for a symbol."""
        resp = self._request("GET", f"/v1/public/funding_rate/{symbol}")
        return resp.get("data", {})

    def get_funding_rates_all(self) -> List[Dict[str, Any]]:
        """Get funding rates for all symbols by querying each."""
        symbols = self.get_futures_info()
        rates = []
        for s in symbols:
            sym = s.get("symbol", "")
            if not sym:
                continue
            try:
                rate = self.get_funding_rate(sym)
                if rate:
                    rate["symbol"] = sym
                    rates.append(rate)
            except Exception:
                continue
        return rates
    
    # ── Private endpoints ──
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account info (maintenance margin ratio, etc.)."""
        resp = self._request("GET", "/v1/client/info")
        return resp.get("data", {})
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions with PnL."""
        resp = self._request("GET", "/v1/positions")
        rows = resp.get("data", {}).get("rows", [])
        # Filter to actual open positions
        return [p for p in rows if float(p.get("position_qty", 0)) != 0]
    
    def get_holding(self) -> Dict[str, Any]:
        """Get collateral holding (USDC balance)."""
        resp = self._request("GET", "/v1/client/holding")
        return resp.get("data", {})

    def get_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get all open orders, optionally filtered by symbol."""
        path = "/v1/orders?status=INCOMPLETE"
        if symbol:
            path += f"&symbol={symbol}"
        resp = self._request("GET", path)
        return resp.get("data", {}).get("rows", [])
    
    def place_order(
        self, 
        symbol: str, 
        side: str, 
        order_type: str, 
        order_quantity: float, 
        order_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Place a market or limit order."""
        order_data = {
            "symbol": symbol,
            "side": side.upper(),
            "order_type": order_type.upper(),
            "order_quantity": order_quantity,
        }
        if order_price is not None:
            order_data["order_price"] = order_price
            
        resp = self._request("POST", "/v1/order", order_data)
        return resp.get("data", {})
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an open order."""
        resp = self._request("DELETE", f"/v1/order?symbol={symbol}&order_id={order_id}")
        return resp.get("data", {})

    def close(self):
        """Close the HTTP client."""
        self._client.close()
