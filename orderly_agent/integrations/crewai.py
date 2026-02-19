"""
CrewAI tools for trading on Orderly Network.

Usage:
    from orderly_agent.integrations.crewai import ORDERLY_TOOLS, orderly_trader_agent
    agent = orderly_trader_agent()
"""

from typing import List, Optional
from ._client import OrderlyClient
from . import _format as fmt

try:
    from crewai.tools import tool
    from crewai import Agent
except ImportError:
    raise ImportError("crewai required. Install: pip install crewai")

_client: Optional[OrderlyClient] = None

def _get_client() -> OrderlyClient:
    global _client
    if _client is None:
        _client = OrderlyClient()
    return _client


@tool("orderly_place_order")
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
    """
    try:
        result = _get_client().place_order(symbol, side, order_type, quantity, price)
        return f"✅ Order placed — ID: {result.get('order_id')}, status: {result.get('status', 'NEW')}"
    except Exception as e:
        return f"❌ Order failed: {e}"


@tool("orderly_get_positions")
def orderly_get_positions() -> str:
    """Get all open perpetual futures positions with unrealized PnL, entry/mark prices, and liquidation prices."""
    try:
        return fmt.format_positions(_get_client().get_positions())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool("orderly_get_markets")
def orderly_get_markets() -> str:
    """List all available perpetual futures trading pairs on Orderly Network."""
    try:
        return fmt.format_markets(_get_client().get_futures_info())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool("orderly_get_orderbook")
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


@tool("orderly_account_info")
def orderly_account_info() -> str:
    """Get account balance, margin info, and USDC collateral."""
    try:
        c = _get_client()
        return fmt.format_account(c.get_account_info(), c.get_holding())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool("orderly_cancel_order")
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


@tool("orderly_get_funding_rates")
def orderly_get_funding_rates() -> str:
    """Get current predicted funding rates for all perpetual futures. Positive = longs pay shorts."""
    try:
        return fmt.format_funding_rates(_get_client().get_funding_rates_all())
    except Exception as e:
        return f"❌ Failed: {e}"


@tool("orderly_get_open_orders")
def orderly_get_open_orders(symbol: str = None) -> str:
    """Get all pending/open orders, optionally filtered by symbol.

    Args:
        symbol: Optional filter (e.g. 'PERP_ETH_USDC'). Omit for all orders.
    """
    try:
        return fmt.format_open_orders(_get_client().get_open_orders(symbol))
    except Exception as e:
        return f"❌ Failed: {e}"


ORDERLY_TOOLS = [
    orderly_place_order,
    orderly_get_positions,
    orderly_get_markets,
    orderly_get_orderbook,
    orderly_account_info,
    orderly_cancel_order,
    orderly_get_funding_rates,
    orderly_get_open_orders,
]


def orderly_trader_agent(llm: str = None) -> Agent:
    """Create a pre-configured CrewAI Agent for trading on Orderly Network.

    Args:
        llm: Optional model string (e.g. 'anthropic/claude-sonnet-4-20250514')
    """
    kwargs = dict(
        role="Perpetual Futures Trader",
        goal="Execute trades on Orderly Network while managing risk. Always check positions and account before trading.",
        backstory=(
            "Expert DeFi trader on Orderly Network, a cross-chain perpetual futures exchange. "
            "You understand orderbook dynamics, funding rates, and position management. "
            "You always verify account balance and existing positions before placing new orders. "
            "You consider funding rates when deciding to hold positions."
        ),
        tools=ORDERLY_TOOLS,
        verbose=True,
        allow_delegation=False,
        max_iter=10,
    )
    if llm:
        kwargs["llm"] = llm
    return Agent(**kwargs)
