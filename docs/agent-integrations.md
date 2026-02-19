# AI Agent Integrations for Orderly Network

Deploy AI trading agents on Orderly Network with LangChain, CrewAI, or AutoGen in minutes.

## 🚀 Quick Start

### Prerequisites

```bash
# Install the SDK
pip install agent-trading-sdk

# Install your preferred AI framework  
pip install langchain-core    # For LangChain
pip install crewai           # For CrewAI
pip install pyautogen        # For AutoGen

# Required dependencies
pip install httpx PyNaCl
```

### Environment Setup

```bash
export ORDERLY_ACCOUNT_ID="your-account-id"
export ORDERLY_PRIVATE_KEY="your-base64-private-key"  
export ORDERLY_API_BASE="https://api-evm.orderly.org"  # Optional
```

## 🦜 LangChain Integration

### Basic Usage (5 lines)

```python
from orderly_agent.integrations.langchain import get_orderly_tools
from langchain.agents import initialize_agent, AgentType
from langchain.llms import OpenAI

tools = get_orderly_tools()
agent = initialize_agent(tools, OpenAI(), agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
```

### Available Tools

- `orderly_place_order()` - Place market/limit orders
- `orderly_get_positions()` - View open positions with P&L
- `orderly_get_markets()` - List trading pairs with 24h stats
- `orderly_get_orderbook()` - Get L2 orderbook data
- `orderly_account_info()` - Check balance and margin
- `orderly_cancel_order()` - Cancel open orders
- `orderly_get_funding_rates()` - Current funding rates

### Example: Trading Bot

```python
from orderly_agent.integrations.langchain import get_orderly_tools
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

# Setup
tools = get_orderly_tools()
llm = ChatOpenAI(model="gpt-4")

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a DeFi trading expert. Always check positions and account info before trading."),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_openai_functions_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# Trade!
result = executor.invoke({"input": "Buy 0.1 ETH at market price"})
```

## 🚢 CrewAI Integration

### Deploy a Trading Agent in 5 Minutes

```python
from orderly_agent.integrations.crewai import orderly_trader_agent
from crewai import Crew, Task

agent = orderly_trader_agent()
crew = Crew(agents=[agent], tasks=[Task(description="Buy 0.1 ETH", agent=agent)])
```

### Pre-built Trading Agent

The `orderly_trader_agent()` returns a fully configured CrewAI agent with:

- **Role**: DeFi Trading Specialist
- **Goal**: Execute profitable trades while managing risk
- **Tools**: All Orderly trading functions
- **Memory**: Enabled for context retention
- **Backstory**: Expert knowledge of DeFi and risk management

### Custom Agent Example

```python
from orderly_agent.integrations.crewai import ORDERLY_TOOLS
from crewai import Agent, Task, Crew

# Create custom agent
trader = Agent(
    role="Momentum Trader",
    goal="Identify and trade momentum breakouts on Orderly Network",
    backstory="You specialize in momentum trading strategies...",
    tools=ORDERLY_TOOLS,
    verbose=True
)

# Define trading task
task = Task(
    description="""
    Analyze ETH/USDC market conditions and execute a momentum trade:
    1. Check current positions and account balance
    2. Get ETH/USDC orderbook and recent price action
    3. If momentum is bullish, place a small long position
    4. Set appropriate risk management
    """,
    agent=trader
)

# Execute
crew = Crew(agents=[trader], tasks=[task])
result = crew.kickoff()
```

### Multi-Agent Trading System

```python
from orderly_agent.integrations.crewai import ORDERLY_TOOLS, orderly_trader_agent
from crewai import Agent, Task, Crew

# Analyst agent (no trading tools)
analyst = Agent(
    role="Market Analyst", 
    goal="Provide market analysis and trading signals",
    backstory="You analyze market trends and provide trading recommendations",
    tools=[],  # No trading tools, just analysis
)

# Trader agent (with trading tools)
trader = orderly_trader_agent()

# Risk manager
risk_manager = Agent(
    role="Risk Manager",
    goal="Monitor positions and enforce risk limits", 
    backstory="You ensure trades stay within risk parameters",
    tools=ORDERLY_TOOLS,  # Can check positions and cancel orders
)

# Define workflow
tasks = [
    Task(description="Analyze ETH market conditions", agent=analyst),
    Task(description="Execute trades based on analysis", agent=trader),
    Task(description="Monitor and manage risk", agent=risk_manager),
]

crew = Crew(agents=[analyst, trader, risk_manager], tasks=tasks)
result = crew.kickoff()
```

## 🤖 AutoGen Integration

### Basic Setup (5 lines)

```python
from orderly_agent.integrations.autogen import register_orderly_tools
import autogen

agent = autogen.AssistantAgent(name="trader", llm_config={"model": "gpt-4"})
register_orderly_tools(agent)
```

### Multi-Agent Trading System

```python
import autogen
from orderly_agent.integrations.autogen import register_orderly_tools

# Configure LLM
llm_config = {
    "model": "gpt-4",
    "api_key": "your-openai-key"
}

# Create agents
user_proxy = autogen.UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    code_execution_config={"use_docker": False}
)

trader = autogen.AssistantAgent(
    name="trader",
    llm_config=llm_config,
    system_message="You are a professional DeFi trader. Always check positions before trading."
)

risk_manager = autogen.AssistantAgent(
    name="risk_manager", 
    llm_config=llm_config,
    system_message="You monitor trading risk and can halt trading if needed."
)

# Register trading tools with both agents
register_orderly_tools(trader)
register_orderly_tools(risk_manager)

# Create group chat
group_chat = autogen.GroupChat(
    agents=[user_proxy, trader, risk_manager],
    messages=[],
    max_round=10
)

manager = autogen.GroupChatManager(group_chat=group_chat, llm_config=llm_config)

# Start trading conversation
user_proxy.initiate_chat(
    manager,
    message="I want to buy some ETH. Please check the market and execute a small trade."
)
```

## 📊 Common Trading Patterns

### Position Management

```python
# Check current positions
positions = agent.run("Get my current positions")

# Check account balance  
account = agent.run("Show my account balance")

# Place a limit order
order = agent.run("Place a limit buy order for 0.5 ETH at $2400")

# Cancel an order
cancel = agent.run("Cancel order ID 12345")
```

### Market Analysis

```python
# Get available markets
markets = agent.run("Show all available trading pairs")

# Check orderbook depth
orderbook = agent.run("Get orderbook for PERP_ETH_USDC with 5 levels")

# Check funding rates
funding = agent.run("What are the current funding rates?")
```

### Risk Management

```python
# Always check positions first
risk_prompt = """
Before making any trades:
1. Check current positions and P&L
2. Verify account balance and margin usage
3. Consider position sizing (max 10% of account per trade)
4. Set stop losses if needed
"""
```

## 🔧 Configuration

### Custom API Endpoints

```python
from orderly_agent.integrations._client import OrderlyConfig, OrderlyClient

# Custom configuration
config = OrderlyConfig(
    account_id="your-account-id",
    private_key="your-private-key", 
    api_base="https://testnet-api-evm.orderly.org"  # Testnet
)

# Pass to integrations (advanced usage)
client = OrderlyClient(config)
```

### Error Handling

All tools return human-readable error messages:

```python
# Example error responses
"❌ Order failed: Insufficient balance"
"❌ Failed to get positions: Invalid API key"
"📊 No open positions found."
```

## 🎯 Best Practices

### 1. Always Check Before Trading
```python
"Before placing any orders, check my current positions and account balance"
```

### 2. Use Appropriate Position Sizing
```python
"Place a limit order for 1% of my account balance in ETH"
```

### 3. Consider Market Conditions
```python
"Check the ETH orderbook and funding rates before buying"
```

### 4. Implement Risk Management
```python
"Set a stop loss at 2% below entry price"
```

### 5. Monitor Active Positions
```python
"Check my positions every hour and close any with >5% loss"
```

## 🚨 Risk Warnings

- **Start Small**: Test with small positions first
- **Use Testnet**: Practice on testnet before mainnet
- **Monitor Closely**: AI agents can make rapid trades
- **Set Limits**: Use account-level position limits
- **Understand Costs**: Consider funding rates and fees

## 🆘 Troubleshooting

### Common Issues

1. **Import Errors**: Install required dependencies
   ```bash
   pip install httpx PyNaCl langchain-core crewai pyautogen
   ```

2. **Authentication Errors**: Check environment variables
   ```bash
   echo $ORDERLY_ACCOUNT_ID
   echo $ORDERLY_PRIVATE_KEY
   ```

3. **API Errors**: Verify account has trading permissions

4. **Tool Registration**: Ensure proper framework-specific setup

### Getting Help

- Check the [main SDK documentation](../README.md)
- Review example code in `/examples`
- Open issues on GitHub for bugs
- Use testnet for development and testing

---

**Ready to trade?** Pick your framework above and start building AI trading agents on Orderly Network! 🚀