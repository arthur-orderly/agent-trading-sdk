"""
AI Agent integrations for Orderly Network trading.

This package provides trading tools for popular AI agent frameworks:
- LangChain: Tools with @tool decorators
- CrewAI: Tools and pre-built agent
- AutoGen: Function registration system

Quick Start Examples:

# LangChain
from orderly_agent.integrations.langchain import get_orderly_tools
tools = get_orderly_tools()

# CrewAI  
from orderly_agent.integrations.crewai import ORDERLY_TOOLS, orderly_trader_agent
agent = orderly_trader_agent()

# AutoGen
from orderly_agent.integrations.autogen import register_orderly_tools
register_orderly_tools(my_agent)
"""

__version__ = "0.1.0"
__all__ = []

# Optional: Import main functions for convenience
try:
    from .langchain import get_orderly_tools
    __all__.append("get_orderly_tools")
except ImportError:
    pass

try:
    from .crewai import ORDERLY_TOOLS, orderly_trader_agent
    __all__.extend(["ORDERLY_TOOLS", "orderly_trader_agent"])
except ImportError:
    pass

try:
    from .autogen import register_orderly_tools
    __all__.append("register_orderly_tools")
except ImportError:
    pass