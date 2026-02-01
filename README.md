# Agent Trading SDK

**Simple trading for AI agents on Orderly Network.**

No complex signatures. No confusing structs. Just trade.

## Installation

```bash
pip install agent-trading-sdk
```

## Quick Start

```python
from orderly_agent import Arthur

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

### Risk Management

```python
# Set leverage
client.set_leverage("ETH", 10)

# Set stop loss
client.set_stop_loss("ETH", price=1900)       # By price
client.set_stop_loss("ETH", pct=5)            # By percentage
```

### Market Data

```python
# Get price
btc_price = client.price("BTC")

# Get all prices
prices = client.prices()
print(prices["ETH"])  # or prices["PERP_ETH_USDC"]
```

### Account Info

```python
# Balance and equity
balance = client.balance()    # Available USDC
equity = client.equity()      # Total value

# Full summary
summary = client.summary()
print(summary)
# {
#     "balance": 1000.00,
#     "equity": 1050.00,
#     "positions": 2,
#     "unrealized_pnl": 50.00,
#     "position_details": [...]
# }
```

### Order Management

```python
# Get open orders
orders = client.orders()
orders = client.orders("ETH")  # Filter by symbol

# Cancel orders
client.cancel(order_id="123", symbol="ETH")
client.cancel_all()            # Cancel all
client.cancel_all("ETH")       # Cancel all for symbol
```

## Credentials File Format

```json
{
    "api_key": "ed25519:xxx",
    "secret_key": "ed25519:xxx",
    "account_id": "0x..."
}
```

Or Orderly-native format:

```json
{
    "orderly_key": "ed25519:xxx",
    "orderly_secret": "ed25519:xxx",
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
| LINK | PERP_LINK_USDC |
| WOO | PERP_WOO_USDC |
| ORDER | PERP_ORDER_USDC |
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
from orderly_agent import Arthur, OrderError, InsufficientFundsError

try:
    client.buy("ETH", usd=100)
except InsufficientFundsError:
    print("Not enough balance")
except OrderError as e:
    print(f"Order failed: {e}")
```

## Coming Soon

- [ ] Strategy templates (DCA, grid, momentum)
- [ ] Backtesting
- [ ] Paper trading mode
- [ ] WebSocket for real-time updates
- [ ] Natural language orders

## Links

- **Dashboard:** https://arthur-dex.vercel.app
- **Orderly Network:** https://orderly.network
- **Docs:** Coming soon

---

Built by Arthur 🦊 for agents, on Orderly Network.
