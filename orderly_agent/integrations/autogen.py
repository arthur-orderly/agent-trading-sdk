"""
AutoGen tools for trading on Orderly Network.

Usage:
    from orderly_agent.integrations.autogen import register_orderly_tools
    register_orderly_tools(agent, executor)
"""

from typing import Optional
from ._client import OrderlyClient
from . import _format as fmt

_client: Optional[OrderlyClient] = None

def _get_client() -> OrderlyClient:
    global _client
    if _client is None:
        _client = OrderlyClient()
    return _client


# ── Tool functions ──

def orderly_place_order(symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> str:
    """Place an order on Orderly Network. side=BUY/SELL, order_type=MARKET/LIMIT."""
    try:
        result = _get_client().place_order(symbol, side, order_type, quantity, price)
        return f"✅ Order placed — ID: {result.get('order_id')}, status: {result.get('status', 'NEW')}"
    except Exception as e:
        return f"❌ Order failed: {e}"

def orderly_get_positions() -> str:
    """Get all open positions with PnL."""
    try:
        return fmt.format_positions(_get_client().get_positions())
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_get_markets() -> str:
    """List available perpetual futures on Orderly Network."""
    try:
        return fmt.format_markets(_get_client().get_futures_info())
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_get_orderbook(symbol: str, depth: int = 10) -> str:
    """Get L2 orderbook for a symbol."""
    try:
        return fmt.format_orderbook(symbol, _get_client().get_orderbook(symbol, depth))
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_account_info() -> str:
    """Get account balance and margin info."""
    try:
        c = _get_client()
        return fmt.format_account(c.get_account_info(), c.get_holding())
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_cancel_order(symbol: str, order_id: int) -> str:
    """Cancel an open order by symbol and order_id."""
    try:
        _get_client().cancel_order(symbol, order_id)
        return f"✅ Order {order_id} cancelled."
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_get_funding_rates() -> str:
    """Get current funding rates for all perps."""
    try:
        return fmt.format_funding_rates(_get_client().get_funding_rates_all())
    except Exception as e:
        return f"❌ Failed: {e}"

def orderly_get_open_orders(symbol: str = None) -> str:
    """Get pending orders, optionally filtered by symbol."""
    try:
        return fmt.format_open_orders(_get_client().get_open_orders(symbol))
    except Exception as e:
        return f"❌ Failed: {e}"


# ── AutoGen registration ──

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "orderly_place_order", "description": "Place a buy/sell order on Orderly Network perp DEX", "parameters": {"type": "object", "properties": {"symbol": {"type": "string", "description": "e.g. PERP_BTC_USDC"}, "side": {"type": "string", "enum": ["BUY", "SELL"]}, "order_type": {"type": "string", "enum": ["MARKET", "LIMIT"]}, "quantity": {"type": "number"}, "price": {"type": "number", "description": "Required for LIMIT orders"}}, "required": ["symbol", "side", "order_type", "quantity"]}}},
    {"type": "function", "function": {"name": "orderly_get_positions", "description": "Get all open positions with PnL", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "orderly_get_markets", "description": "List available trading pairs", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "orderly_get_orderbook", "description": "Get L2 orderbook", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "depth": {"type": "integer", "default": 10}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "orderly_account_info", "description": "Get account balance and margin", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "orderly_cancel_order", "description": "Cancel an open order", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "order_id": {"type": "integer"}}, "required": ["symbol", "order_id"]}}},
    {"type": "function", "function": {"name": "orderly_get_funding_rates", "description": "Get funding rates for all perps", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "orderly_get_open_orders", "description": "Get pending orders", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}}}}
]

FUNCTION_MAP = {
    "orderly_place_order": orderly_place_order,
    "orderly_get_positions": orderly_get_positions,
    "orderly_get_markets": orderly_get_markets,
    "orderly_get_orderbook": orderly_get_orderbook,
    "orderly_account_info": orderly_account_info,
    "orderly_cancel_order": orderly_cancel_order,
    "orderly_get_funding_rates": orderly_get_funding_rates,
    "orderly_get_open_orders": orderly_get_open_orders,
}


def register_orderly_tools(agent, executor=None) -> None:
    """Register all Orderly trading tools with an AutoGen agent.

    Args:
        agent: AutoGen AssistantAgent
        executor: Optional UserProxyAgent for tool execution
    """
    try:
        from autogen import register_function
        target_executor = executor or agent
        for schema in TOOL_SCHEMAS:
            name = schema["function"]["name"]
            register_function(
                FUNCTION_MAP[name],
                caller=agent,
                executor=target_executor,
                name=name,
                description=schema["function"]["description"],
            )
    except ImportError:
        # Fallback for older AutoGen
        if hasattr(agent, 'update_function_signature'):
            agent.update_function_signature(TOOL_SCHEMAS, is_remove=False)
            if executor and hasattr(executor, 'register_function'):
                executor.register_function(function_map=FUNCTION_MAP)
        else:
            raise ImportError("AutoGen (pyautogen>=0.2.0) required. Install: pip install pyautogen")
