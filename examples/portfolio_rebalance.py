#!/usr/bin/env python3
"""
Portfolio Rebalancer

Maintains target allocations across multiple assets.
Rebalances when drift exceeds threshold.

Example allocations:
- BTC: 50%
- ETH: 30%
- SOL: 20%
"""

import time
from orderly_agent import Arthur


def main():
    client = Arthur.from_credentials_file("credentials.json")
    
    # Target allocations (must sum to 100)
    targets = {
        "BTC": 50,
        "ETH": 30,
        "SOL": 20
    }
    
    rebalance_threshold = 5  # Rebalance when drift > 5%
    check_interval = 3600    # Check every hour
    
    print("📊 Portfolio Rebalancer")
    print(f"   Targets: {targets}")
    print(f"   Threshold: {rebalance_threshold}%")
    print()
    
    while True:
        try:
            # Get account equity
            summary = client.summary()
            total_equity = summary["equity"]
            
            print(f"💰 Total Equity: ${total_equity:,.2f}")
            
            # Calculate current allocations
            positions = {p.symbol.replace("PERP_", "").replace("_USDC", ""): p 
                        for p in client.positions()}
            
            current = {}
            for symbol in targets:
                if symbol in positions:
                    pos = positions[symbol]
                    value = abs(pos.size * pos.mark_price)
                    current[symbol] = (value / total_equity) * 100 if total_equity > 0 else 0
                else:
                    current[symbol] = 0
            
            # Check drift and rebalance
            print("\n   Symbol  Target  Current   Drift")
            print("   " + "-" * 35)
            
            needs_rebalance = False
            for symbol in targets:
                target_pct = targets[symbol]
                current_pct = current.get(symbol, 0)
                drift = current_pct - target_pct
                
                flag = "⚠️" if abs(drift) > rebalance_threshold else "✓"
                print(f"   {symbol:6} {target_pct:6.1f}%  {current_pct:6.1f}%  {drift:+6.1f}% {flag}")
                
                if abs(drift) > rebalance_threshold:
                    needs_rebalance = True
            
            if needs_rebalance:
                print("\n🔄 Rebalancing portfolio...")
                
                for symbol in targets:
                    target_pct = targets[symbol]
                    current_pct = current.get(symbol, 0)
                    
                    target_value = total_equity * target_pct / 100
                    current_value = total_equity * current_pct / 100
                    diff = target_value - current_value
                    
                    if abs(diff) < 10:  # Skip if diff is tiny
                        continue
                    
                    if diff > 0:
                        # Need to increase position
                        print(f"   📈 Buying ${diff:.2f} of {symbol}")
                        client.buy(symbol, usd=diff)
                    else:
                        # Need to decrease position
                        print(f"   📉 Selling ${abs(diff):.2f} of {symbol}")
                        # Check if we have a position to reduce
                        if symbol in positions:
                            pos = positions[symbol]
                            if pos.side == "LONG":
                                # Close some of the long
                                reduce_size = abs(diff) / pos.mark_price
                                client.close(symbol, size=min(reduce_size, pos.size))
                
                print("   ✅ Rebalance complete!")
            else:
                print("\n✅ Portfolio balanced - no action needed")
            
            print(f"\n💰 Total PnL: ${client.pnl():.2f}")
            print("-" * 40)
            
            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping rebalancer...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
