# AI Agent Integrations

This directory contains integrations for popular AI agent frameworks:

## 🦜 LangChain (`langchain.py`)
- Tools with `@tool` decorators
- `get_orderly_tools()` function returns all tools
- Compatible with LangChain agents and chains

## 🚢 CrewAI (`crewai.py`) 
- Tools with `@tool` decorators
- `ORDERLY_TOOLS` list for easy import
- `orderly_trader_agent()` pre-built agent
- Optimized for multi-agent workflows

## 🤖 AutoGen (`autogen.py`)
- `register_orderly_tools(agent, executor)` function
- Compatible with AutoGen's function calling system
- Supports both v0.2+ and legacy registration

## 🔧 Shared Client (`_client.py`)
- Common `OrderlyClient` used by all integrations
- Handles authentication and API calls
- Environment-based configuration

## 📚 Available Tools

All integrations provide these 7 core trading tools:

1. **`orderly_place_order`** - Place market/limit orders
2. **`orderly_get_positions`** - View open positions with P&L  
3. **`orderly_get_markets`** - List available trading pairs
4. **`orderly_get_orderbook`** - Get L2 orderbook data
5. **`orderly_account_info`** - Check balance and margin
6. **`orderly_cancel_order`** - Cancel open orders
7. **`orderly_get_funding_rates`** - Current funding rates

## 🚀 Quick Start

```python
# LangChain
from orderly_agent.integrations.langchain import get_orderly_tools

# CrewAI  
from orderly_agent.integrations.crewai import ORDERLY_TOOLS, orderly_trader_agent

# AutoGen
from orderly_agent.integrations.autogen import register_orderly_tools
```

See `/docs/agent-integrations.md` for complete examples and deployment guides.