#!/usr/bin/env python3
"""
Momentum Trading Strategy

A trend-following strategy that:
- Goes long when price breaks above recent highs
- Goes short when price breaks below recent lows
- Uses trailing stops to lock in profits

Good for trending markets.
"""

import time
from orderly_agent import Arthur


def main():
    client = Arthur.from_credentials_file("credentials.json")
    
    symbol = "BTC"
    position_size_usd = 200
    lookback_periods = 20
    trail_percent = 2.0  # 2% trailing stop
    
    price_history = []
    highest_since_entry = 0
    lowest_since_entry = float('inf')
    entry_price = 0
    
    print(f"🚀 Momentum Strategy on {symbol}")
    print(f"   Lookback: {lookback_periods} periods")
    print(f"   Trail: {trail_percent}%")
    print()
    
    while True:
        try:
            price = client.price(symbol)
            price_history.append(price)
            
            if len(price_history) > lookback_periods + 10:
                price_history = price_history[-(lookback_periods + 10):]
            
            if len(price_history) < lookback_periods:
                print(f"⏳ Collecting data... {len(price_history)}/{lookback_periods}")
                time.sleep(60)
                continue
            
            # Calculate breakout levels
            recent = price_history[-lookback_periods:]
            high = max(recent)
            low = min(recent)
            
            position = client.position(symbol)
            
            if position:
                # Update trailing stop tracking
                if position.side == "LONG":
                    highest_since_entry = max(highest_since_entry, price)
                    trail_price = highest_since_entry * (1 - trail_percent / 100)
                    
                    if price < trail_price:
                        client.close(symbol)
                        pnl = (price - entry_price) / entry_price * 100
                        print(f"📤 Trail stop hit! Closed LONG at ${price:,.2f} ({pnl:+.1f}%)")
                        highest_since_entry = 0
                        entry_price = 0
                    else:
                        print(f"📈 LONG | ${price:,.2f} | Trail: ${trail_price:,.2f} | PnL: ${position.unrealized_pnl:.2f}")
                
                else:  # SHORT
                    lowest_since_entry = min(lowest_since_entry, price)
                    trail_price = lowest_since_entry * (1 + trail_percent / 100)
                    
                    if price > trail_price:
                        client.close(symbol)
                        pnl = (entry_price - price) / entry_price * 100
                        print(f"📤 Trail stop hit! Closed SHORT at ${price:,.2f} ({pnl:+.1f}%)")
                        lowest_since_entry = float('inf')
                        entry_price = 0
                    else:
                        print(f"📉 SHORT | ${price:,.2f} | Trail: ${trail_price:,.2f} | PnL: ${position.unrealized_pnl:.2f}")
            
            else:
                # Look for breakout
                if price > high:
                    client.buy(symbol, usd=position_size_usd)
                    entry_price = price
                    highest_since_entry = price
                    print(f"🚀 BREAKOUT UP! Long {symbol} at ${price:,.2f}")
                
                elif price < low:
                    client.sell(symbol, usd=position_size_usd)
                    entry_price = price
                    lowest_since_entry = price
                    print(f"💥 BREAKOUT DOWN! Short {symbol} at ${price:,.2f}")
                
                else:
                    print(f"⏳ Range: ${low:,.2f} - ${high:,.2f} | Price: ${price:,.2f}")
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping strategy...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)
    
    print(f"\n📊 Final PnL: ${client.pnl():.2f}")


if __name__ == "__main__":
    main()
