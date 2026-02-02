#!/usr/bin/env python3
"""
Grid Trading Strategy

Places buy and sell orders at fixed price intervals.
Profits from price oscillation in a range.

Great for sideways/ranging markets.
"""

import time
from orderly_agent import Arthur


def main():
    client = Arthur.from_credentials_file("credentials.json")
    
    symbol = "ETH"
    grid_size = 10          # Number of grid levels
    grid_spacing_pct = 1.0  # 1% between levels
    order_size_usd = 50     # USD per grid order
    
    # Get current price as center
    center_price = client.price(symbol)
    
    # Calculate grid levels
    levels = []
    for i in range(-grid_size // 2, grid_size // 2 + 1):
        if i == 0:
            continue
        price = center_price * (1 + i * grid_spacing_pct / 100)
        levels.append({
            "price": price,
            "side": "BUY" if i < 0 else "SELL",
            "filled": False
        })
    
    print(f"📊 Grid Trading on {symbol}")
    print(f"   Center: ${center_price:,.2f}")
    print(f"   Levels: {grid_size}")
    print(f"   Spacing: {grid_spacing_pct}%")
    print(f"\n   Grid:")
    for level in sorted(levels, key=lambda x: -x["price"]):
        print(f"   ${level['price']:,.2f} - {level['side']}")
    print()
    
    while True:
        try:
            price = client.price(symbol)
            
            # Check each grid level
            for level in levels:
                if level["filled"]:
                    continue
                
                # Check if price crossed this level
                if level["side"] == "BUY" and price <= level["price"]:
                    client.buy(symbol, usd=order_size_usd, price=level["price"])
                    level["filled"] = True
                    print(f"📈 Grid BUY at ${level['price']:,.2f}")
                    
                elif level["side"] == "SELL" and price >= level["price"]:
                    client.sell(symbol, usd=order_size_usd, price=level["price"])
                    level["filled"] = True
                    print(f"📉 Grid SELL at ${level['price']:,.2f}")
            
            # Status
            filled_count = sum(1 for l in levels if l["filled"])
            position = client.position(symbol)
            pos_str = f"{position.side} {position.size}" if position else "None"
            
            print(f"💹 ${price:,.2f} | Filled: {filled_count}/{len(levels)} | Pos: {pos_str} | PnL: ${client.pnl():.2f}")
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping grid...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)
    
    # Cancel any open orders
    client.cancel_all()
    print(f"\n📊 Final PnL: ${client.pnl():.2f}")


if __name__ == "__main__":
    main()
