# Arthur SDK

**The easiest way for AI agents to trade crypto perpetuals.**

3 lines of Python. No complex signatures. No confusing structs. Just trade.

```python
from orderly_agent import Arthur
client = Arthur.from_credentials_file("credentials.json")
client.buy("ETH", usd=100)  # Done.
```

## Why Arthur?

- 🚀 **Dead simple** - Trade in 3 lines of code
- 🤖 **Built for agents** - Clean API, no boilerplate
- ⚡ **Fast execution** - Powered by Orderly Network
- 📊 **50+ markets** - BTC, ETH, SOL, ARB, and more
- 🔒 **Non-custodial** - Your keys, your coins

## Installation

```bash
pip install agent-trading-sdk
```

## Quick Start

```python
from orderly_agent import Arthur

# Load credentials
client = Arthur.from_credentials_file("credentials.json")

# Trade
client.buy("ETH", usd=100)      # Long $100 of ETH
client.sell("BTC", size=0.01)   # Short 0.01 BTC
client.close("ETH")             # Close position
client.close_all()              # Close everything

# Check status
print(client.balance())         # Available USDC
print(client.pnl())             # Total unrealized PnL
print(client.positions())       # All open positions
```

## Strategy Examples

### RSI Strategy
```python
# Buy oversold, sell overbought
if rsi < 30:
    client.buy("ETH", usd=100)
elif rsi > 70:
    client.sell("ETH", usd=100)
```
👉 [Full RSI example](examples/rsi_strategy.py)

### Momentum Strategy
```python
# Trend following with trailing stops
if price > recent_high:
    client.buy("BTC", usd=200)
```
👉 [Full momentum example](examples/momentum_strategy.py)

### Grid Trading
```python
# Profit from sideways markets
for level in grid_levels:
    client.buy(symbol, price=level, usd=50)
```
👉 [Full grid example](examples/grid_trading.py)

### AI Agent
```python
# Let your LLM make decisions
context = get_market_context(client, ["BTC", "ETH"])
decision = llm.chat(TRADING_PROMPT, context)
execute_trade(client, decision)
```
👉 [Full AI agent example](examples/ai_agent.py)

### Portfolio Rebalancer
```python
# Maintain target allocations
targets = {"BTC": 50, "ETH": 30, "SOL": 20}
rebalance_portfolio(client, targets)
```
👉 [Full rebalancer example](examples/portfolio_rebalance.py)

## API Reference

### Trading

```python
# Market orders
client.buy("ETH", usd=100)      # Buy by USD value
client.buy("BTC", size=0.01)    # Buy by size

# Limit orders
client.buy("ETH", size=0.1, price=2000)

# Close positions
client.close("ETH")             # Close all of symbol
client.close("ETH", size=0.05)  # Partial close
client.close_all()              # Close everything
```

### Position Management

```python
# Get all positions
for pos in client.positions():
    print(f"{pos.symbol}: {pos.side} {pos.size}")
    print(f"  Entry: ${pos.entry_price}")
    print(f"  PnL: ${pos.unrealized_pnl} ({pos.pnl_percent}%)")

# Get specific position
eth_pos = client.position("ETH")

# Total PnL
total_pnl = client.pnl()
```

### Market Data

```python
# Get price
btc_price = client.price("BTC")

# Get all prices
prices = client.prices()
```

### Account Info

```python
balance = client.balance()    # Available USDC
equity = client.equity()      # Total value
summary = client.summary()    # Full details
```

### Risk Management

```python
client.set_leverage("ETH", 10)
client.set_stop_loss("ETH", price=1900)
client.set_stop_loss("ETH", pct=5)  # 5% stop
```

## Credentials

Create a `credentials.json`:

```json
{
    "api_key": "ed25519:xxx",
    "secret_key": "ed25519:xxx",
    "account_id": "0x..."
}
```

Get credentials from [Arthur DEX](https://arthurdex.com) or any Orderly-powered DEX.

## Supported Markets

Short symbols work automatically:

| Short | Full Symbol |
|-------|-------------|
| BTC | PERP_BTC_USDC |
| ETH | PERP_ETH_USDC |
| SOL | PERP_SOL_USDC |
| ARB, OP, AVAX, LINK... | PERP_*_USDC |

50+ perpetual markets available.

## Testnet

```python
client = Arthur(..., testnet=True)
```

## Error Handling

```python
from orderly_agent import Arthur, OrderError, InsufficientFundsError

try:
    client.buy("ETH", usd=100)
except InsufficientFundsError:
    print("Not enough balance")
except OrderError as e:
    print(f"Order failed: {e}")
```

## Links

- **Trade:** [arthurdex.com](https://arthurdex.com)
- **Twitter:** [@Arthur_Orderly](https://twitter.com/Arthur_Orderly)
- **Orderly Network:** [orderly.network](https://orderly.network)

## License

MIT

---

Built by Arthur 🤖 for AI agents, powered by Orderly Network.
