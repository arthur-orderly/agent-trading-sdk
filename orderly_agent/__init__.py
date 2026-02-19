"""
Agent Trading SDK - Simple trading for AI agents on Orderly Network.

Usage:
    # Core SDK
    from orderly_agent import Arthur
    
    client = Arthur(api_key="your_key")
    client.buy("ETH", usd=100)
    
    # Or run strategies
    from orderly_agent import StrategyRunner
    runner = StrategyRunner(client)
    runner.run("strategy.json")
    
    # AI Agent Framework Integrations
    from orderly_agent.integrations.langchain import get_orderly_tools      # LangChain
    from orderly_agent.integrations.crewai import orderly_trader_agent      # CrewAI
    from orderly_agent.integrations.autogen import register_orderly_tools   # AutoGen
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
