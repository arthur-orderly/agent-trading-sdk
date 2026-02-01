#!/usr/bin/env python3
"""
Arthur CLI - Run trading strategies from command line.

Replaces ATP executor with a cleaner interface.

Usage:
    arthur run strategies/unlockoor.json --credentials secrets/woofi.json
    arthur run strategies/unlockoor.json --dry-run
    arthur status --credentials secrets/woofi.json
    arthur price BTC ETH SOL
"""

import argparse
import json
import sys
from pathlib import Path

from .client import Arthur
from .strategies import StrategyRunner, StrategyConfig


def cmd_run(args):
    """Run a trading strategy"""
    # Load client
    client = Arthur.from_credentials_file(args.credentials)
    
    # Create runner
    runner = StrategyRunner(
        client,
        dry_run=args.dry_run,
        on_signal=lambda s: print(f"Signal: {s.action} {s.symbol} - {s.reason}"),
        on_trade=lambda t: print(f"Trade: {t}"),
    )
    
    # Run strategy
    if args.loop:
        print(f"Running {args.strategy} every {args.interval}s (Ctrl+C to stop)")
        try:
            runner.run_loop(args.strategy, interval=args.interval)
        except KeyboardInterrupt:
            print("\nStopped")
    else:
        result = runner.run(args.strategy, force=True)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Strategy: {result['strategy']}")
            print(f"Symbol: {result['symbol']}")
            if result.get('signal'):
                sig = result['signal']
                print(f"Signal: {sig['action']} - {sig['reason']}")
            if result.get('trade'):
                trade = result['trade']
                print(f"Trade: {trade['status']} - Order {trade.get('order_id', 'N/A')}")
            if result.get('error'):
                print(f"Error: {result['error']}")


def cmd_status(args):
    """Show account status"""
    client = Arthur.from_credentials_file(args.credentials)
    
    summary = client.summary()
    
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Balance: ${summary['balance']:,.2f}")
        print(f"Equity: ${summary['equity']:,.2f}")
        print(f"Unrealized PnL: ${summary['unrealized_pnl']:,.2f}")
        print(f"Open Positions: {summary['positions']}")
        
        if summary['position_details']:
            print("\nPositions:")
            for pos in summary['position_details']:
                pnl_sign = "+" if pos['pnl'] >= 0 else ""
                print(f"  {pos['symbol']}: {pos['side']} {pos['size']:.4f}")
                print(f"    Entry: ${pos['entry']:,.2f} → ${pos['mark']:,.2f}")
                print(f"    PnL: {pnl_sign}${pos['pnl']:,.2f} ({pnl_sign}{pos['pnl_pct']:.1f}%)")


def cmd_price(args):
    """Get current prices"""
    client = Arthur()  # No auth needed for prices
    
    prices = {}
    for symbol in args.symbols:
        try:
            prices[symbol] = client.price(symbol)
        except Exception as e:
            prices[symbol] = f"Error: {e}"
    
    if args.json:
        print(json.dumps(prices, indent=2))
    else:
        for symbol, price in prices.items():
            if isinstance(price, float):
                print(f"{symbol}: ${price:,.2f}")
            else:
                print(f"{symbol}: {price}")


def cmd_trade(args):
    """Execute a trade"""
    client = Arthur.from_credentials_file(args.credentials)
    
    if args.dry_run:
        print(f"[DRY RUN] Would {args.action} {args.symbol}")
        price = client.price(args.symbol)
        if args.usd:
            size = args.usd / price
            print(f"  Size: {size:.6f} @ ${price:,.2f} = ${args.usd:.2f}")
        elif args.size:
            print(f"  Size: {args.size} @ ${price:,.2f} = ${args.size * price:.2f}")
        return
    
    try:
        if args.action == "buy":
            order = client.buy(args.symbol, size=args.size, usd=args.usd)
        elif args.action == "sell":
            order = client.sell(args.symbol, size=args.size, usd=args.usd)
        elif args.action == "close":
            order = client.close(args.symbol, size=args.size)
        
        if order:
            print(f"✅ Order {order.order_id}")
            print(f"   {order.side} {order.size:.6f} {order.symbol}")
            print(f"   Status: {order.status}")
        else:
            print("No order placed (no position to close?)")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Arthur SDK - Simple trading for AI agents"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run a trading strategy")
    run_parser.add_argument("strategy", help="Path to strategy JSON file")
    run_parser.add_argument("-c", "--credentials", default="~/.config/arthur/credentials.json",
                           help="Path to credentials file")
    run_parser.add_argument("--dry-run", action="store_true", help="Don't execute trades")
    run_parser.add_argument("--loop", action="store_true", help="Run continuously")
    run_parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    run_parser.add_argument("--json", action="store_true", help="Output as JSON")
    run_parser.set_defaults(func=cmd_run)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show account status")
    status_parser.add_argument("-c", "--credentials", default="~/.config/arthur/credentials.json",
                              help="Path to credentials file")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")
    status_parser.set_defaults(func=cmd_status)
    
    # Price command
    price_parser = subparsers.add_parser("price", help="Get current prices")
    price_parser.add_argument("symbols", nargs="+", help="Symbols to check (e.g., BTC ETH)")
    price_parser.add_argument("--json", action="store_true", help="Output as JSON")
    price_parser.set_defaults(func=cmd_price)
    
    # Trade command
    trade_parser = subparsers.add_parser("trade", help="Execute a trade")
    trade_parser.add_argument("action", choices=["buy", "sell", "close"], help="Trade action")
    trade_parser.add_argument("symbol", help="Symbol to trade (e.g., ETH)")
    trade_parser.add_argument("--size", type=float, help="Position size")
    trade_parser.add_argument("--usd", type=float, help="Position size in USD")
    trade_parser.add_argument("-c", "--credentials", default="~/.config/arthur/credentials.json",
                             help="Path to credentials file")
    trade_parser.add_argument("--dry-run", action="store_true", help="Don't execute trade")
    trade_parser.set_defaults(func=cmd_trade)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
