#!/usr/bin/env python3
"""
Basic trading example with Arthur SDK.
"""

from arthur import Arthur


def main():
    # Load credentials from file
    client = Arthur.from_credentials_file("~/.config/arthur/credentials.json")
    
    # Or initialize directly
    # client = Arthur(
    #     api_key="ed25519:xxx",
    #     secret_key="ed25519:xxx",
    #     account_id="0x..."
    # )
    
    # Get account summary
    print("=== Account Summary ===")
    summary = client.summary()
    print(f"Balance: ${summary['balance']:.2f}")
    print(f"Equity: ${summary['equity']:.2f}")
    print(f"Unrealized PnL: ${summary['unrealized_pnl']:.2f}")
    print(f"Open Positions: {summary['positions']}")
    
    # Get current prices
    print("\n=== Prices ===")
    print(f"BTC: ${client.price('BTC'):,.2f}")
    print(f"ETH: ${client.price('ETH'):,.2f}")
    print(f"SOL: ${client.price('SOL'):,.2f}")
    
    # Show positions
    print("\n=== Positions ===")
    for pos in client.positions():
        symbol = pos.symbol.replace("PERP_", "").replace("_USDC", "")
        print(f"{symbol}: {pos.side} {pos.size} @ ${pos.entry_price:.2f}")
        print(f"  Mark: ${pos.mark_price:.2f}, PnL: ${pos.unrealized_pnl:.2f} ({pos.pnl_percent:.1f}%)")
    
    # Example trades (commented out for safety)
    # client.buy("ETH", usd=100)     # Buy $100 worth of ETH
    # client.sell("BTC", size=0.01)  # Sell 0.01 BTC
    # client.close("ETH")            # Close ETH position
    # client.close_all()             # Close all positions


if __name__ == "__main__":
    main()
