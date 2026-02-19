#!/usr/bin/env python3
"""
Example: AI Agent Framework Integrations for Orderly Network

This script demonstrates how to use the Orderly SDK with different AI agent frameworks.
It shows mock examples that would work if you have the frameworks installed.
"""

import os

def demo_environment_setup():
    """Show how to set up environment variables"""
    print("🔧 Environment Setup:")
    print("export ORDERLY_ACCOUNT_ID='your-account-id'")
    print("export ORDERLY_PRIVATE_KEY='your-base64-private-key'")
    print("export ORDERLY_API_BASE='https://api-evm.orderly.org'  # Optional")
    print()

def demo_langchain():
    """Demo LangChain integration"""
    print("🦜 LangChain Integration Demo:")
    print("=" * 50)
    
    code = '''
# Install: pip install 'agent-trading-sdk[langchain]' langchain-openai

from orderly_agent.integrations.langchain import get_orderly_tools
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

# Get trading tools
tools = get_orderly_tools()
print(f"Loaded {len(tools)} Orderly trading tools")

# Setup LLM and prompt
llm = ChatOpenAI(model="gpt-4")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a DeFi trading expert. Check positions before trading."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

# Create agent
agent = create_openai_functions_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# Execute trades
result = executor.invoke({
    "input": "Check my account balance and buy 0.1 ETH if I have enough funds"
})
'''
    print(code)

def demo_crewai():
    """Demo CrewAI integration"""
    print("\n🚢 CrewAI Integration Demo:")
    print("=" * 50)
    
    code = '''
# Install: pip install 'agent-trading-sdk[crewai]'

from orderly_agent.integrations.crewai import orderly_trader_agent, ORDERLY_TOOLS
from crewai import Task, Crew

# Option 1: Use pre-built agent
trader = orderly_trader_agent()

# Option 2: Create custom agent  
from crewai import Agent

custom_trader = Agent(
    role="Scalp Trader",
    goal="Execute quick scalping trades on high-volume pairs",
    backstory="Expert in short-term trading strategies...",
    tools=ORDERLY_TOOLS,  # All 7 trading tools
    verbose=True
)

# Create trading task
task = Task(
    description="""
    Execute a conservative long position in ETH:
    1. Check current account balance and positions
    2. Analyze ETH/USDC market (orderbook, funding rates)  
    3. If conditions are favorable, place a small long position
    4. Report the trade execution results
    """,
    agent=trader
)

# Run the crew
crew = Crew(agents=[trader], tasks=[task])
result = crew.kickoff()
print(result)
'''
    print(code)

def demo_autogen():
    """Demo AutoGen integration"""  
    print("\n🤖 AutoGen Integration Demo:")
    print("=" * 50)
    
    code = '''
# Install: pip install 'agent-trading-sdk[autogen]'

import autogen
from orderly_agent.integrations.autogen import register_orderly_tools

# Configure agents
llm_config = {"model": "gpt-4", "api_key": "your-openai-key"}

user_proxy = autogen.UserProxyAgent(
    name="user",
    human_input_mode="NEVER"
)

trader = autogen.AssistantAgent(
    name="trader",
    llm_config=llm_config,
    system_message="You are a professional DeFi trader on Orderly Network."
)

# Register Orderly trading tools
register_orderly_tools(trader)

# Start conversation
user_proxy.initiate_chat(
    trader,
    message="Check my positions and place a small ETH long if account allows"
)
'''
    print(code)

def demo_multi_agent_system():
    """Demo multi-agent trading system"""
    print("\n🤝 Multi-Agent Trading System Demo:")
    print("=" * 50)
    
    code = '''
# Advanced: Multi-agent system with specialized roles

from orderly_agent.integrations.crewai import ORDERLY_TOOLS
from crewai import Agent, Task, Crew

# 1. Market Analyst (no trading tools, just analysis)
analyst = Agent(
    role="Market Analyst",
    goal="Analyze market conditions and provide trading signals", 
    backstory="Expert in technical analysis and market trends",
    tools=[],  # No trading tools
)

# 2. Trader (executes trades)
trader = Agent(
    role="Execution Trader", 
    goal="Execute trades based on analyst recommendations",
    backstory="Skilled at efficient order execution",
    tools=ORDERLY_TOOLS,  # All trading tools
)

# 3. Risk Manager (monitors positions)
risk_manager = Agent(
    role="Risk Manager",
    goal="Monitor positions and enforce risk limits",
    backstory="Conservative risk management expert", 
    tools=ORDERLY_TOOLS,  # Can check/close positions
)

# Define workflow
tasks = [
    Task(
        description="Analyze ETH market: price action, volume, funding rates",
        agent=analyst
    ),
    Task(
        description="Execute trade based on analysis, max 2% of account", 
        agent=trader
    ),
    Task(
        description="Monitor position, close if loss exceeds 1%",
        agent=risk_manager
    )
]

# Execute multi-agent workflow
crew = Crew(agents=[analyst, trader, risk_manager], tasks=tasks)
result = crew.kickoff()
'''
    print(code)

def main():
    """Run all demos"""
    print("🤖 Orderly SDK - AI Agent Integration Examples\n")
    
    demo_environment_setup()
    demo_langchain()
    demo_crewai()
    demo_autogen()
    demo_multi_agent_system()
    
    print("\n" + "=" * 60)
    print("📚 Next Steps:")
    print("1. Set up your environment variables")
    print("2. Install your preferred AI framework")
    print("3. Copy and modify the examples above")
    print("4. Start with testnet for development")
    print("5. Check the docs: /docs/agent-integrations.md")
    print("\n🚀 Happy trading!")

if __name__ == "__main__":
    main()