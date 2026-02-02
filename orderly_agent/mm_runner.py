#!/usr/bin/env python3
"""
ORDER Market Maker Runner v3

Fixed in v3:
- Actually cancels old orders before requoting
- Hard stop loss at account level
- Better inventory management
- Tracks session PnL properly

Usage:
    python3 -m orderly_agent.mm_runner strategies/order-mm.json secrets/randy-orderly.json
"""

import json
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from .client import Arthur
from .auth import generate_auth_headers


@dataclass
class MMState:
    """Market maker state"""
    last_prices: List[float] = field(default_factory=list)
    last_quote_time: float = 0
    session_start: float = 0
    starting_balance: float = 0
    order_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        self.session_start = time.time()


def load_config(path: str) -> dict:
    """Load MM config from JSON"""
    with open(Path(path).expanduser()) as f:
        return json.load(f)


def load_creds(path: str) -> dict:
    """Load credentials from JSON"""
    with open(Path(path).expanduser()) as f:
        return json.load(f)


def calculate_volatility(prices: List[float]) -> float:
    """Calculate price volatility as % range"""
    if len(prices) < 2:
        return 0
    return ((max(prices) - min(prices)) / prices[-1]) * 100


def cancel_all_orders(creds: dict, symbol: str) -> bool:
    """Cancel all orders for symbol using correct API"""
    try:
        path = f"/v1/orders?symbol=PERP_{symbol}_USDC"
        headers = generate_auth_headers(
            api_key=creds['key'],
            secret_key=creds['secret_key'],
            account_id=creds['account_id'],
            method="DELETE",
            path=path
        )
        # Must use this content type for DELETE
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        
        req = urllib.request.Request(
            f"https://api-evm.orderly.org{path}",
            method="DELETE",
            headers=headers
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get('success', False)
    except Exception as e:
        print(f"  Warning: cancel failed - {e}")
        return False


def get_unsettled_pnl(creds: dict, symbol: str) -> float:
    """Get unsettled PnL for symbol"""
    try:
        path = "/v1/positions"
        headers = generate_auth_headers(
            api_key=creds['key'],
            secret_key=creds['secret_key'],
            account_id=creds['account_id'],
            method="GET",
            path=path
        )
        
        req = urllib.request.Request(
            f"https://api-evm.orderly.org{path}",
            headers=headers
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            
        if result.get('success'):
            for p in result['data'].get('rows', []):
                if p.get('symbol') == f"PERP_{symbol}_USDC":
                    return float(p.get('unsettled_pnl', 0))
        return 0
    except:
        return 0


def get_total_collateral(creds: dict) -> float:
    """Get total collateral value (actual balance after unsettled PnL)"""
    try:
        path = "/v1/positions"
        headers = generate_auth_headers(
            api_key=creds['key'],
            secret_key=creds['secret_key'],
            account_id=creds['account_id'],
            method="GET",
            path=path
        )
        
        req = urllib.request.Request(
            f"https://api-evm.orderly.org{path}",
            headers=headers
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            
        if result.get('success'):
            return float(result['data'].get('total_collateral_value', 0))
        return 0
    except:
        return 0


def run_mm_cycle(client: Arthur, config: dict, state: MMState, creds: dict) -> dict:
    """Run one market making cycle"""
    
    result = {
        "timestamp": int(time.time() * 1000),
        "action": None,
        "orders": [],
        "position": None,
        "pnl": 0,
    }
    
    symbol = config["symbol"]
    mm = config["market_making"]
    vol_cfg = config.get("volatility", {})
    risk = config["risk"]
    
    try:
        # 0. Check account-level stop loss first
        current_collateral = get_total_collateral(creds)
        if state.starting_balance == 0:
            state.starting_balance = current_collateral
            
        session_pnl = current_collateral - state.starting_balance
        result["session_pnl"] = session_pnl
        result["collateral"] = current_collateral
        
        # Hard stop: if we've lost more than daily_loss_limit, stop everything
        daily_loss_limit = risk.get("daily_loss_limit_usd", 30)
        if session_pnl <= -daily_loss_limit:
            result["action"] = "daily_loss_limit_hit"
            # Cancel all orders and close position
            cancel_all_orders(creds, symbol)
            try:
                client.close(symbol)
            except:
                pass
            return result
        
        # 1. Cancel ALL existing orders before doing anything
        cancel_all_orders(creds, symbol)
        time.sleep(0.5)  # Brief pause for cancels to process
        
        # 2. Get market data
        spread_info = client.spread(symbol)
        mid = spread_info["mid"]
        market_spread_bps = spread_info["spread_bps"]
        
        result["mid"] = mid
        result["market_spread_bps"] = market_spread_bps
        
        # Track prices for volatility
        state.last_prices.append(mid)
        state.last_prices = state.last_prices[-30:]  # Keep last 30
        
        # 3. Calculate volatility
        volatility = calculate_volatility(state.last_prices)
        result["volatility_pct"] = volatility
        
        # Check if volatility too high - pause
        if vol_cfg.get("enabled") and volatility > vol_cfg.get("pause_threshold_pct", 5):
            result["action"] = "paused_high_volatility"
            return result
        
        # 4. Get current position
        position = client.position(symbol)
        inventory_usd = 0
        if position:
            inventory_usd = position.size * mid
            if position.side == "SHORT":
                inventory_usd = -inventory_usd
            
            result["position"] = {
                "side": position.side,
                "size": position.size,
                "entry": position.entry_price,
                "pnl": position.unrealized_pnl,
                "pnl_pct": position.pnl_percent,
            }
            
            # 5. Check position-level stop loss
            if position.pnl_percent <= -risk["stop_loss_pct"]:
                result["action"] = "stop_loss_triggered"
                try:
                    client.close(symbol)
                    result["closed"] = True
                except Exception as e:
                    result["error"] = str(e)
                return result
            
            # Check take profit
            if position.pnl_percent >= risk.get("take_profit_pct", 100):
                result["action"] = "take_profit_triggered"
                try:
                    client.close(symbol)
                    result["closed"] = True
                except Exception as e:
                    result["error"] = str(e)
                return result
        
        result["inventory_usd"] = inventory_usd
        
        # 6. Calculate spread with adjustments
        base_spread = mm["base_spread_bps"]
        
        # Volatility adjustment
        if vol_cfg.get("enabled") and volatility > vol_cfg.get("threshold_pct", 1.5):
            spread_mult = vol_cfg.get("spread_multiplier", 2.0)
            base_spread = base_spread * spread_mult
            result["volatility_adjusted"] = True
        
        # Cap spread
        base_spread = min(base_spread, mm.get("max_spread_bps", 100))
        base_spread = max(base_spread, mm["min_spread_bps"])
        
        # 7. Calculate inventory skew
        skew_bps = (inventory_usd / 100) * mm.get("skew_per_100_usd", 10)
        result["skew_bps"] = skew_bps
        
        # 8. Calculate quote prices
        half_spread = (base_spread / 10000) * mid / 2
        skew_amount = (skew_bps / 10000) * mid
        
        # Skew: if long, lower bid more (discourage more longs), raise ask less
        # if short, raise ask more, lower bid less
        bid_price = mid - half_spread - skew_amount
        ask_price = mid + half_spread - skew_amount
        
        # Ensure minimum spread
        min_spread = (mm["min_spread_bps"] / 10000) * mid
        if ask_price - bid_price < min_spread:
            gap = min_spread - (ask_price - bid_price)
            bid_price -= gap / 2
            ask_price += gap / 2
        
        # Round to tick
        bid_price = round(bid_price, 5)
        ask_price = round(ask_price, 5)
        
        # Calculate size
        size = mm["order_size_usd"] / mid
        size = max(1, round(size))
        
        result["quotes"] = {
            "bid": bid_price,
            "ask": ask_price,
            "size": size,
            "spread_bps": ((ask_price - bid_price) / mid) * 10000,
        }
        
        # 9. Check if we should skip a side due to max inventory
        place_bid = True
        place_ask = True
        
        max_inv = risk["max_position_usd"]
        if inventory_usd >= max_inv * 0.8:
            place_bid = False  # Don't buy more if already very long
        if inventory_usd <= -max_inv * 0.8:
            place_ask = False  # Don't sell more if already very short
        
        # 10. Place orders
        if not config["flags"].get("dry_run"):
            if place_bid:
                try:
                    order = client.limit_buy(symbol, price=bid_price, size=size)
                    result["orders"].append({"side": "BID", "price": bid_price, "id": order.order_id})
                except Exception as e:
                    result["bid_error"] = str(e)
            
            if place_ask:
                try:
                    order = client.limit_sell(symbol, price=ask_price, size=size)
                    result["orders"].append({"side": "ASK", "price": ask_price, "id": order.order_id})
                except Exception as e:
                    result["ask_error"] = str(e)
            
            result["action"] = "quoted"
        else:
            result["action"] = "dry_run"
        
        state.last_quote_time = time.time()
        
    except Exception as e:
        result["action"] = "error"
        result["error"] = str(e)
        import traceback
        traceback.print_exc()
    
    return result


def format_result(result: dict) -> str:
    """Format result for logging"""
    lines = []
    
    ts = time.strftime("%H:%M:%S")
    action = result.get("action", "unknown")
    
    if action == "quoted":
        q = result.get("quotes", {})
        pos_str = ""
        if result.get("position"):
            p = result["position"]
            pos_str = f" | pos={p['side']} {p['size']:.0f} pnl=${p['pnl']:.2f}"
        
        session_pnl = result.get("session_pnl", 0)
        lines.append(f"[{ts}] QUOTED ${result.get('mid', 0):.5f} | "
                    f"bid/ask ${q.get('bid', 0):.5f}/${q.get('ask', 0):.5f} "
                    f"({q.get('spread_bps', 0):.0f}bps){pos_str} | session=${session_pnl:+.2f}")
        
    elif action == "stop_loss_triggered":
        lines.append(f"[{ts}] 🛑 STOP LOSS TRIGGERED - closing position")
    
    elif action == "take_profit_triggered":
        lines.append(f"[{ts}] 🎯 TAKE PROFIT - closing position")
    
    elif action == "daily_loss_limit_hit":
        lines.append(f"[{ts}] ⛔ DAILY LOSS LIMIT HIT - stopping MM, session=${result.get('session_pnl', 0):.2f}")
    
    elif action == "paused_high_volatility":
        lines.append(f"[{ts}] ⏸️ PAUSED - high volatility ({result.get('volatility_pct', 0):.2f}%)")
    
    elif action == "error":
        lines.append(f"[{ts}] ❌ ERROR: {result.get('error', 'unknown')}")
    
    elif action == "dry_run":
        q = result.get("quotes", {})
        lines.append(f"[{ts}] [DRY] bid/ask ${q.get('bid', 0):.5f}/${q.get('ask', 0):.5f}")
    
    return "\n".join(lines)


def run_once(config_path: str, creds_path: str) -> dict:
    """Run single MM cycle and return result"""
    config = load_config(config_path)
    creds = load_creds(creds_path)
    client = Arthur.from_credentials_file(creds_path)
    state = MMState()
    
    result = run_mm_cycle(client, config, state, creds)
    print(format_result(result))
    
    return result


def run_loop(config_path: str, creds_path: str, duration_sec: Optional[float] = None):
    """Run continuous MM loop"""
    config = load_config(config_path)
    creds = load_creds(creds_path)
    client = Arthur.from_credentials_file(creds_path)
    state = MMState()
    
    interval = config["market_making"]["requote_interval_sec"]
    
    print(f"🤖 ORDER Market Maker v3")
    print(f"   Symbol: {config['symbol']}")
    print(f"   Spread: {config['market_making']['base_spread_bps']} bps")
    print(f"   Size: ${config['market_making']['order_size_usd']}")
    print(f"   Interval: {interval}s")
    print(f"   Daily loss limit: ${config['risk'].get('daily_loss_limit_usd', 30)}")
    print(f"   Mode: {'DRY RUN' if config['flags'].get('dry_run') else 'LIVE'}")
    print("=" * 50)
    
    start = time.time()
    
    try:
        while True:
            result = run_mm_cycle(client, config, state, creds)
            print(format_result(result))
            
            # Stop if daily loss limit hit
            if result.get("action") == "daily_loss_limit_hit":
                print("Stopping due to daily loss limit.")
                break
            
            if duration_sec and (time.time() - start) >= duration_sec:
                break
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n⏹️ Stopping...")
        # Cancel all orders on exit
        cancel_all_orders(creds, config["symbol"])
    
    print(f"\nSession stats:")
    print(f"  Duration: {(time.time() - state.session_start) / 60:.1f} min")
    print(f"  Final collateral: ${get_total_collateral(creds):.2f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m orderly_agent.mm_runner <config.json> <credentials.json> [--loop] [--duration=SEC]")
        sys.exit(1)
    
    config_path = sys.argv[1]
    creds_path = sys.argv[2]
    
    if "--loop" in sys.argv:
        duration = None
        for arg in sys.argv:
            if arg.startswith("--duration="):
                duration = float(arg.split("=")[1])
        run_loop(config_path, creds_path, duration)
    else:
        run_once(config_path, creds_path)
