# Arthur SDK

[![PyPI version](https://badge.fury.io/py/arthur-sdk.svg)](https://badge.fury.io/py/arthur-sdk)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Simple trading for AI agents on Arthur DEX.**

Trade in 3 lines of code. No complex signatures. No confusing structs. Just trade.

```python
from arthur_sdk import Arthur

client = Arthur.from_credentials_file("credentials.json")
client.buy("ETH", usd=100)
```

Built for [Arthur DEX](https://arthurdex.com) on Orderly Network.

## Installation

```bash
pip install arthur-sdk
```

## Quick Start

```python
from arthur_sdk import Arthur

# Initialize with credentials
client = Arthur(
    api_key="ed25519:xxx",
    secret_key="ed25519:xxx",
    account_id="0x..."
)

# Or load from file
client = Arthur.from_credentials_file("credentials.json")

# Trade
client.buy("ETH", usd=100)      # Buy $100 worth of ETH
client.sell("BTC", size=0.01)   # Sell 0.01 BTC
client.close("ETH")             # Close ETH position
client.close_all()              # Close all positions

# Check status
print(client.balance())         # Available USDC
print(client.pnl())             # Total unrealized PnL
print(client.positions())       # All open positions
```

## Features

### Simple Trading

```python
# Market orders (instant execution)
client.buy("ETH", usd=100)      # Buy by USD value
client.buy("BTC", size=0.01)    # Buy by size

# Limit orders
client.buy("ETH", size=0.1, price=2000)

# Close positions
client.close("ETH")             # Close specific position
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

### Market Making

```python
# Place two-sided quotes
quotes = client.quote(
    symbol="ETH",
    bid_price=2000,
    ask_price=2010,
    size=0.1
)

# Post-only limit orders
client.limit_buy("ETH", price=2000, size=0.1, post_only=True)

# Get spread info
spread = client.spread("ETH")
print(f"Spread: {spread['spread_bps']:.1f} bps")
```

### Strategy Execution

```python
from arthur_sdk import StrategyRunner

# Run strategies from JSON configs
runner = StrategyRunner(client)
result = runner.run("strategies/momentum.json")
```

## CLI

```bash
# Get prices
arthur price BTC ETH SOL

# Check account status
arthur status -c credentials.json

# Execute trades
arthur trade buy ETH --usd 100 -c credentials.json

# Run strategies
arthur run strategy.json -c credentials.json
```

## Credentials File

```json
{
    "api_key": "ed25519:xxx",
    "secret_key": "ed25519:xxx",
    "account_id": "0x..."
}
```

## Supported Symbols

Short symbols are automatically converted:

| Short | Full Symbol |
|-------|-------------|
| BTC | PERP_BTC_USDC |
| ETH | PERP_ETH_USDC |
| SOL | PERP_SOL_USDC |
| ARB | PERP_ARB_USDC |
| OP | PERP_OP_USDC |
| AVAX | PERP_AVAX_USDC |
| ... | ... |

## Testnet

```python
client = Arthur(
    api_key="...",
    secret_key="...",
    account_id="...",
    testnet=True  # Use testnet
)
```

## Error Handling

```python
from arthur_sdk import Arthur, OrderError, InsufficientFundsError

try:
    client.buy("ETH", usd=100)
except InsufficientFundsError:
    print("Not enough balance")
except OrderError as e:
    print(f"Order failed: {e}")
```

## Security Model

**Arthur SDK never handles wallet private keys.** Here's what you need to know:

### What the SDK touches

The SDK uses **Orderly ed25519 trading keys** — not your wallet private key. These are:

- `orderly_key` — a public key for API authentication
- `orderly_secret` — a signing key that can place and cancel orders

These keys are created once during account registration on Orderly's own website/frontend, where your wallet signs a message. After that, the wallet private key is never needed again.

### What trading keys CAN do
- Place and cancel orders
- Query positions and balances
- Set leverage

### What trading keys CANNOT do
- **Withdraw funds** — withdrawals require a wallet signature, which this SDK never requests
- **Access other accounts** — keys are scoped to a single Orderly account
- **Bypass Orderly risk limits** — position limits and margin requirements are enforced server-side

### Worst-case scenario

Even if this SDK were fully compromised, an attacker with your trading keys could only place bad trades on your account. They **cannot drain your wallet or withdraw your funds**. Orderly's server-side risk limits (margin requirements, max position sizes) further constrain potential damage.

### Supply chain security

Like any open-source package, you're trusting the maintainers and dependencies. We minimize this risk by:

- **Minimal dependencies** — only `pynacl` (well-audited NaCl/libsodium bindings) is required
- **No network calls outside Orderly** — the SDK only communicates with `api-evm.orderly.org`
- **Open source** — full code is auditable on [GitHub](https://github.com/arthur-orderly/arthur-sdk)
- **Pinned dependency versions** — prevents dependency confusion attacks
- **Input validation** — credential format validation, order size limits, rate limiting built in

### Best practices

1. **Use a dedicated trading account** — don't reuse keys from your main wallet
2. **Set position limits** on Orderly's frontend as an additional guardrail
3. **Start on testnet** — `Arthur(..., testnet=True)`
4. **Pin the SDK version** — `pip install arthur-sdk==0.2.1` instead of auto-updating
5. **Audit the code** — it's ~1,500 lines of Python, fully readable

## Agent API (v0.3.0)

The Agent class wraps the Arthur client with risk guardrails and strategy primitives for autonomous trading.

### Agent Quick Start

```python
from arthur_sdk import Arthur, Agent

client = Arthur.from_credentials_file("credentials.json")
agent = Agent(client, max_drawdown=0.10, max_position_usd=10000)
```

### TWAP Execution

```python
# Buy $5000 ETH over 5 minutes in 10 slices
agent.twap("ETH", "BUY", total_usd=5000, duration=300, slices=10)
```

### Grid Trading

```python
# Place a grid of limit orders from $1900-$2100
agent.grid("ETH", lower=1900, upper=2100, levels=5, size_per_level=0.1)
```

### Portfolio Rebalance

```python
# Rebalance to 60% ETH, 40% BTC
agent.rebalance({"ETH": 0.6, "BTC": 0.4})
```

### Scaled Entry

```python
# Scale into ETH at 3 price levels
agent.scale_in("ETH", "BUY", total_usd=3000, entries=[1950, 1900, 1850])
```

### DCA Schedule

```python
# DCA $100 into ETH every hour (runs in background)
agent.dca("ETH", "BUY", amount_usd=100, interval_seconds=3600)
```

### Risk Guardrails

```python
agent = Agent(client, max_drawdown=0.10, max_position_usd=10000)

# Automatic risk checks before every trade:
# - Drawdown kill-switch: closes all positions if equity drops 10%
# - Position limits: prevents any single position exceeding $10k

# Event callbacks for monitoring
agent.on("drawdown", lambda data: print(f"⚠️ Drawdown: {data['drawdown']:.1%}"))
agent.on("fill", lambda data: print(f"✅ Fill: {data}"))

# Check agent status anytime
print(agent.status())
```

### Event Streaming (Real-time)

```python
from arthur_sdk import Arthur, EventStream

client = Arthur.from_credentials_file("credentials.json")
stream = EventStream(client)

stream.on("fill", lambda data: print(f"Fill: {data}"))
stream.on("position_update", lambda data: print(f"Position: {data}"))
stream.on("liquidation", lambda data: print(f"⚠️ Liquidation: {data}"))

stream.connect(background=True)  # Runs in background thread
```

Requires: `pip install arthur-sdk[realtime]`

### Portfolio Management

```python
from arthur_sdk import Arthur, Portfolio

client = Arthur.from_credentials_file("credentials.json")
portfolio = Portfolio(client)

# Full portfolio snapshot
snap = portfolio.snapshot()
print(f"Equity: ${snap['equity']:.2f}")
print(f"Positions: {snap['num_positions']}")

# Exposure analysis
exp = portfolio.exposure()
print(f"Net exposure: ${exp['net_usd']:.2f}")

# Risk metrics
risk = portfolio.risk_metrics()
print(f"Margin usage: {risk['margin_usage_pct']:.1f}%")
print(f"Max drawdown: {risk['max_drawdown_pct']:.1f}%")

# Equity history
history = portfolio.history(hours=24)
```

### Batch Orders

```python
from arthur_sdk import Arthur, BatchOrder

client = Arthur.from_credentials_file("credentials.json")
batch = BatchOrder()
batch.add("ETH", "BUY", 0.1, price=2000)
batch.add("ETH", "SELL", 0.1, price=2100)
batch.add("BTC", "BUY", 0.001)

results = batch.execute(client)
# Later: batch.cancel_all(client)
```

## Links

- **Arthur DEX:** https://arthurdex.com
- **Documentation:** https://arthurdex.com/docs
- **Orderly Network:** https://orderly.network
- **GitHub:** https://github.com/arthur-orderly/arthur-sdk

## License

MIT

---

Built by Arthur 🦊 for AI agents, on Orderly Network.
