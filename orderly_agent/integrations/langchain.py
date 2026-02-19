"""
LangChain tools for trading on Orderly Network.

Usage:
    from orderly_agent.integrations.langchain import get_orderly_tools
    tools = get_orderly_tools()
"""

from typing import List, Optional
from ._client import OrderlyClient
from . import _format as fmt

try:
    from langchain_core.tools import tool
except ImportError:
    raise ImportError("langchain-core required. Install: pip install langchain-core")

_client: Optional[OrderlyClient] = None

def _get_client() -> OrderlyClient:
    global _client
    if _client is None:
        _client = OrderlyClient()
    return _client


@tool
def orderly_place_order(
    symbol: str, side: str, order_type: str, quantity: float, price: Optional[float] = None
) -> str:
    """Place an order on Orderly Network perpetual futures exchange.

    Args:
        symbol: Trading pair (e.g. 'PERP_BTC_USDC', 'PERP_ETH_USDC', 'PERP_SOL_USDC')
        side: 'BUY' (long) or 'SELL' (short)
        order_type: 'MARKET' (immediate fill) or 'LIMIT' (at specific price)
        quantity: Size in base asset units (e.g. 0.01 BTC, 0.1 ETH)
        price: Required for LIMIT orders. Ignored for MARKET.

    Examples:
        Market buy 0.01 BTC: orderly_place_order("PERP_BTC_USDC", "BUY", "MARKET", 0.01)
        Limit sell 1 ETH at $2500: orderly_place_order("PERP_ETH_USDC", "SELL", "LIMIT", 1.0, 2500.0)
    """
    try:
        result = _get_client().place_order(symbol, side, order_type, quantity, price)
        return f"✅ Order placed — ID: {result.get('order_id')}, status: {result.get('status', 'NEW')}"
    except Exception as e:
        return f"❌ Order failed: {e}"


@tool
def orderly_get_positions() -> str:
    """Get all open perpetual futures positions with unrealized PnL, entry/mark prices, and liquidation prices."""
    try:
        return fmt.format_positions(_get_client().get_positions())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_get_markets() -> str:
    """List all available perpetual futures trading pairs on Orderly Network."""
    try:
        return fmt.format_markets(_get_client().get_futures_info())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_get_orderbook(symbol: str, depth: int = 10) -> str:
    """Get the L2 orderbook for a trading pair showing bids, asks, and spread.

    Args:
        symbol: Trading pair (e.g. 'PERP_ETH_USDC')
        depth: Number of price levels per side (default 10, max 100)
    """
    try:
        return fmt.format_orderbook(symbol, _get_client().get_orderbook(symbol, depth))
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_account_info() -> str:
    """Get account balance, margin info, and USDC collateral."""
    try:
        c = _get_client()
        return fmt.format_account(c.get_account_info(), c.get_holding())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_cancel_order(symbol: str, order_id: int) -> str:
    """Cancel an open order.

    Args:
        symbol: The trading pair of the order (e.g. 'PERP_ETH_USDC')
        order_id: Numeric order ID from order placement or open orders list
    """
    try:
        _get_client().cancel_order(symbol, order_id)
        return f"✅ Order {order_id} cancelled."
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_get_funding_rates() -> str:
    """Get current predicted funding rates for all perpetual futures. Positive = longs pay shorts."""
    try:
        return fmt.format_funding_rates(_get_client().get_funding_rates_all())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool
def orderly_get_open_orders(symbol: str = None) -> str:
    """Get all pending/open orders, optionally filtered by symbol.

    Args:
        symbol: Optional filter (e.g. 'PERP_ETH_USDC'). Omit for all orders.
    """
    try:
        return fmt.format_open_orders(_get_client().get_open_orders(symbol))
    except Exception as e:
        return f"❌ Failed: {e}"


def get_orderly_tools() -> List:
    """Get all Orderly trading tools for LangChain agents."""
    return [
        orderly_place_order,
        orderly_get_positions,
        orderly_get_markets,
        orderly_get_orderbook,
        orderly_account_info,
        orderly_cancel_order,
        orderly_get_funding_rates,
        orderly_get_open_orders,
    ]
