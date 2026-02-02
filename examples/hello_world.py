#!/usr/bin/env python3
"""
Arthur SDK - Hello World

Trade perps in 3 lines of Python.
"""

from orderly_agent import Arthur

client = Arthur.from_credentials_file("credentials.json")
client.buy("ETH", usd=100)
print(f"Bought ETH! PnL: ${client.pnl():.2f}")
