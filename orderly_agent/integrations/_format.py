"""Shared formatting helpers for tool outputs."""

from typing import List, Dict, Any


def format_positions(positions: List[Dict[str, Any]]) -> str:
    if not positions:
        return "📊 No open positions."
    lines = ["📊 Open Positions:\n"]
    for i, p in enumerate(positions, 1):
        sym = p.get("symbol", "?")
        qty = float(p.get("position_qty", 0))
        direction = "LONG" if qty > 0 else "SHORT"
        size = abs(qty)
        entry = float(p.get("average_open_price", 0))
        mark = float(p.get("mark_price", 0))
        pnl = float(p.get("unrealized_pnl", 0))
        pnl_pct = (pnl / (size * entry) * 100) if entry and size else 0
        liq = p.get("est_liq_price", "N/A")
        lines.append(
            f"{i}. {sym} — {direction} {size}\n"
            f"   Entry ${entry:,.2f} | Mark ${mark:,.2f} | Liq ${liq}\n"
            f"   PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%)"
        )
    return "\n".join(lines)


def format_markets(markets: List[Dict[str, Any]]) -> str:
    if not markets:
        return "📈 No markets data."
    lines = ["📈 Available Markets:\n"]
    for m in markets:
        sym = m.get("symbol", "?")
        lines.append(f"  {sym}")
    lines.append(f"\n{len(markets)} markets total.")
    return "\n".join(lines)


def format_orderbook(symbol: str, data: Dict[str, Any]) -> str:
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    if not bids and not asks:
        return f"📚 No orderbook data for {symbol}"
    
    def _price(entry):
        if isinstance(entry, dict): return float(entry.get('price', 0))
        return float(entry[0])
    def _qty(entry):
        if isinstance(entry, dict): return float(entry.get('quantity', 0))
        return float(entry[1])
    
    best_bid = _price(bids[0]) if bids else 0
    best_ask = _price(asks[0]) if asks else 0
    spread = best_ask - best_bid
    spread_bps = (spread / best_ask * 10000) if best_ask else 0
    
    lines = [f"📚 {symbol} Orderbook (spread: {spread_bps:.1f}bps)\n"]
    lines.append("  ASKS:")
    for a in reversed(asks[:10]):
        lines.append(f"    ${_price(a):,.2f}  {_qty(a):.4f}")
    lines.append(f"  ── spread ${spread:,.2f} ──")
    lines.append("  BIDS:")
    for b in bids[:10]:
        lines.append(f"    ${_price(b):,.2f}  {_qty(b):.4f}")
    return "\n".join(lines)


def format_funding_rates(rates: List[Dict[str, Any]]) -> str:
    if not rates:
        return "💸 No funding rate data."
    lines = ["💸 Funding Rates (per 8h):\n"]
    # Sort by absolute rate descending
    sorted_rates = sorted(rates, key=lambda r: abs(float(r.get("est_funding_rate", 0))), reverse=True)
    for r in sorted_rates[:20]:
        sym = r.get("symbol", "?")
        rate = float(r.get("est_funding_rate", 0))
        ann = rate * 3 * 365 * 100  # annualized
        direction = "longs pay" if rate > 0 else "shorts pay" if rate < 0 else "neutral"
        lines.append(f"  {sym}: {rate*100:+.4f}% ({ann:+.1f}% ann) — {direction}")
    return "\n".join(lines)


def format_account(info: Dict[str, Any], holding: Dict[str, Any] = None) -> str:
    lines = ["💰 Account:\n"]
    for key in ["maintenance_margin_ratio", "account_mode", "max_leverage"]:
        val = info.get(key)
        if val is not None:
            lines.append(f"  {key}: {val}")
    if holding:
        h = holding.get("holding", [])
        for asset in h:
            token = asset.get("token", "?")
            total = float(asset.get("holding", 0))
            lines.append(f"  {token}: {total:,.2f}")
    return "\n".join(lines)


def format_open_orders(orders: List[Dict[str, Any]]) -> str:
    if not orders:
        return "📋 No open orders."
    lines = ["📋 Open Orders:\n"]
    for o in orders:
        oid = o.get("order_id", "?")
        sym = o.get("symbol", "?")
        side = o.get("side", "?")
        otype = o.get("type", "?")
        qty = o.get("quantity", 0)
        price = o.get("price", "MARKET")
        status = o.get("status", "?")
        lines.append(f"  #{oid} {sym} {side} {otype} qty={qty} @ {price} [{status}]")
    return "\n".join(lines)
