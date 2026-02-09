"""
Arthur SDK - Simple trading for AI agents on Arthur DEX.

Trade in 3 lines:
    from arthur_sdk import Arthur
    client = Arthur.from_credentials_file("creds.json")
    client.buy("ETH", usd=100)

Learn more: https://arthurdex.com
"""

from .client import Arthur, Position, Order
from .strategies import StrategyRunner, StrategyConfig, Signal, run_strategy
from .exceptions import ArthurError, AuthError, OrderError, InsufficientFundsError
from .market_maker import MarketMaker
from .agent import Agent
from .batch import BatchOrder
from .events import EventStream
from .portfolio import Portfolio

__version__ = "0.3.0"
__all__ = [
    # Core
    "Arthur",
    "Position",
    "Order",
    # Agent API (v0.3.0)
    "Agent",
    "BatchOrder",
    "EventStream",
    "Portfolio",
    # Strategies
    "StrategyRunner",
    "StrategyConfig",
    "Signal",
    "run_strategy",
    # Market Making
    "MarketMaker",
    # Exceptions
    "ArthurError",
    "AuthError",
    "OrderError",
    "InsufficientFundsError",
]
