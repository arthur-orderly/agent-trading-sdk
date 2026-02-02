#!/usr/bin/env python3
"""
AI Trading Agent

Example of integrating Arthur SDK with an LLM for trading decisions.
The AI analyzes market conditions and decides when to trade.

Works with any LLM that has a chat completion API (OpenAI, Anthropic, etc.)
"""

import json
import time
from orderly_agent import Arthur

# Replace with your preferred LLM client
# from openai import OpenAI
# from anthropic import Anthropic


SYSTEM_PROMPT = """You are an AI trading agent managing a crypto perpetual futures portfolio.

You analyze market data and decide on trades. Be conservative - only trade when you have conviction.

Available actions:
- BUY <symbol> <usd_amount> - Go long (e.g., "BUY ETH 100")
- SELL <symbol> <usd_amount> - Go short (e.g., "SELL BTC 200")
- CLOSE <symbol> - Close position (e.g., "CLOSE ETH")
- HOLD - Do nothing

Respond with ONLY one action and a brief reason. Example:
BUY ETH 100
ETH showing strong momentum with BTC stable, good risk/reward for a long.
"""


def get_market_context(client: Arthur, symbols: list[str]) -> str:
    """Build market context for the AI."""
    lines = ["=== Market Context ==="]
    
    # Account info
    summary = client.summary()
    lines.append(f"\nAccount:")
    lines.append(f"  Balance: ${summary['balance']:.2f}")
    lines.append(f"  Equity: ${summary['equity']:.2f}")
    lines.append(f"  Unrealized PnL: ${summary['unrealized_pnl']:.2f}")
    
    # Prices
    lines.append(f"\nPrices:")
    for sym in symbols:
        lines.append(f"  {sym}: ${client.price(sym):,.2f}")
    
    # Positions
    positions = client.positions()
    if positions:
        lines.append(f"\nOpen Positions:")
        for pos in positions:
            sym = pos.symbol.replace("PERP_", "").replace("_USDC", "")
            lines.append(f"  {sym}: {pos.side} {pos.size} @ ${pos.entry_price:.2f}")
            lines.append(f"    PnL: ${pos.unrealized_pnl:.2f} ({pos.pnl_percent:.1f}%)")
    else:
        lines.append(f"\nNo open positions.")
    
    return "\n".join(lines)


def parse_ai_response(response: str) -> tuple[str, str, float | None]:
    """Parse AI response into action, symbol, amount."""
    lines = response.strip().split("\n")
    action_line = lines[0].upper().strip()
    
    if action_line == "HOLD":
        return "HOLD", "", None
    
    parts = action_line.split()
    action = parts[0]
    symbol = parts[1] if len(parts) > 1 else ""
    amount = float(parts[2]) if len(parts) > 2 else None
    
    return action, symbol, amount


def execute_trade(client: Arthur, action: str, symbol: str, amount: float | None):
    """Execute the AI's trading decision."""
    if action == "BUY" and symbol and amount:
        client.buy(symbol, usd=amount)
        print(f"✅ Executed: BUY {symbol} ${amount}")
    elif action == "SELL" and symbol and amount:
        client.sell(symbol, usd=amount)
        print(f"✅ Executed: SELL {symbol} ${amount}")
    elif action == "CLOSE" and symbol:
        client.close(symbol)
        print(f"✅ Executed: CLOSE {symbol}")
    elif action == "HOLD":
        print(f"⏸️ Holding...")
    else:
        print(f"⚠️ Unknown action: {action}")


def main():
    # Initialize trading client
    client = Arthur.from_credentials_file("credentials.json")
    
    # Initialize LLM client (uncomment your choice)
    # llm = OpenAI()  # Uses OPENAI_API_KEY env var
    # llm = Anthropic()  # Uses ANTHROPIC_API_KEY env var
    
    symbols = ["BTC", "ETH", "SOL"]
    check_interval = 300  # 5 minutes
    
    print("🤖 AI Trading Agent Started")
    print(f"   Watching: {', '.join(symbols)}")
    print(f"   Interval: {check_interval}s")
    print()
    
    while True:
        try:
            # Get market context
            context = get_market_context(client, symbols)
            print(context)
            print()
            
            # === REPLACE THIS WITH YOUR LLM CALL ===
            # response = llm.chat.completions.create(
            #     model="gpt-4",
            #     messages=[
            #         {"role": "system", "content": SYSTEM_PROMPT},
            #         {"role": "user", "content": context}
            #     ]
            # ).choices[0].message.content
            
            # For demo, just hold
            response = "HOLD\nDemo mode - no LLM configured."
            # ========================================
            
            print(f"🧠 AI Decision: {response.split(chr(10))[0]}")
            if len(response.split('\n')) > 1:
                print(f"   Reason: {response.split(chr(10))[1]}")
            
            # Parse and execute
            action, symbol, amount = parse_ai_response(response)
            execute_trade(client, action, symbol, amount)
            
            print(f"\n💰 Total PnL: ${client.pnl():.2f}")
            print("-" * 40)
            
            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping agent...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(30)
    
    # Final summary
    print(f"\n📊 Final Account Summary:")
    summary = client.summary()
    print(f"   Balance: ${summary['balance']:.2f}")
    print(f"   PnL: ${summary['unrealized_pnl']:.2f}")


if __name__ == "__main__":
    main()
