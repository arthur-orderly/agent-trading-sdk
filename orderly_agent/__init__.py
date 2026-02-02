"""
Agent Trading SDK - Simple trading for AI agents on Orderly Network.

Usage:
    from orderly_agent import Arthur
    
    client = Arthur(api_key="your_key")
    client.buy("ETH", usd=100)
    
    # Or run strategies
    from orderly_agent import StrategyRunner
    runner = StrategyRunner(client)
    runner.run("strategy.json")
"""

from .client import Arthur, Position, Order
from .strategies import StrategyRunner, StrategyConfig, Signal, run_strategy
from .exceptions import ArthurError, AuthError, OrderError, InsufficientFundsError, WithdrawalError

__version__ = "0.1.0"
__all__ = [
    # Core
    "Arthur",
    "Position", 
    "Order",
    # Strategies
    "StrategyRunner",
    "StrategyConfig",
    "Signal",
    "run_strategy",
    # Exceptions
    "ArthurError",
    "AuthError",
    "OrderError",
    "InsufficientFundsError",
    "WithdrawalError",
]
