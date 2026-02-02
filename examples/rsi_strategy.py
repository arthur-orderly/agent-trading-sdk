#!/usr/bin/env python3
"""
RSI Trading Strategy

A simple RSI-based strategy that:
- Goes long when RSI drops below 30 (oversold)
- Goes short when RSI rises above 70 (overbought)
- Closes positions when RSI returns to neutral (40-60)

Perfect for ranging markets.
"""

import time
from orderly_agent import Arthur


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI from price history."""
    if len(prices) < period + 1:
        return 50.0  # Neutral if not enough data
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def main():
    client = Arthur.from_credentials_file("credentials.json")
    
    symbol = "ETH"
    position_size_usd = 100
    rsi_oversold = 30
    rsi_overbought = 70
    
    price_history = []
    
    print(f"🤖 RSI Strategy on {symbol}")
    print(f"   Oversold: <{rsi_oversold} (buy)")
    print(f"   Overbought: >{rsi_overbought} (sell)")
    print()
    
    while True:
        try:
            # Get current price
            price = client.price(symbol)
            price_history.append(price)
            
            # Keep only last 50 prices
            if len(price_history) > 50:
                price_history = price_history[-50:]
            
            # Calculate RSI
            rsi = calculate_rsi(price_history)
            
            # Get current position
            position = client.position(symbol)
            has_long = position and position.side == "LONG"
            has_short = position and position.side == "SHORT"
            
            # Trading logic
            if rsi < rsi_oversold and not has_long:
                if has_short:
                    client.close(symbol)
                    print(f"📤 Closed short")
                client.buy(symbol, usd=position_size_usd)
                print(f"📈 RSI={rsi:.1f} - LONG {symbol}")
                
            elif rsi > rsi_overbought and not has_short:
                if has_long:
                    client.close(symbol)
                    print(f"📤 Closed long")
                client.sell(symbol, usd=position_size_usd)
                print(f"📉 RSI={rsi:.1f} - SHORT {symbol}")
                
            elif 40 < rsi < 60 and position:
                client.close(symbol)
                print(f"📤 RSI={rsi:.1f} - Closed position")
            
            else:
                print(f"⏳ RSI={rsi:.1f} | ${price:,.2f} | PnL: ${client.pnl():.2f}")
            
            time.sleep(60)  # Check every minute
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping strategy...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)
    
    # Show final state
    print(f"\n📊 Final PnL: ${client.pnl():.2f}")


if __name__ == "__main__":
    main()
