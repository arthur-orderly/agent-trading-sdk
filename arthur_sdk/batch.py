"""
Batch order submission for Arthur SDK.

Build and execute multiple orders efficiently.

Example:
    from arthur_sdk import Arthur, BatchOrder

    client = Arthur.from_credentials_file("creds.json")
    batch = BatchOrder()
    batch.add("ETH", "BUY", 0.1, price=2000)
    batch.add("ETH", "SELL", 0.1, price=2100)
    batch.add("BTC", "BUY", 0.001)
    results = batch.execute(client)
"""

import time
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("arthur_sdk.batch")


class BatchOrder:
    """
    Batch order builder and executor.

    Collects orders and submits them efficiently, using Orderly's batch
    endpoint when available, or sequential submission with rate limiting.

    Example:
        batch = BatchOrder()
        batch.add("ETH", "BUY", 0.1, price=2000)
        batch.add("ETH", "SELL", 0.1, price=2100)
        results = batch.execute(client)
        print(f"Submitted {len(results)} orders")
    """

    def __init__(self):
        """Initialize an empty batch."""
        self._orders: List[Dict[str, Any]] = []
        self._results: List[Any] = []
        self._order_ids: List[str] = []

    def add(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
    ) -> "BatchOrder":
        """
        Add an order to the batch.

        Args:
            symbol: Token symbol (e.g., "ETH" or "PERP_ETH_USDC").
            side: "BUY" or "SELL".
            size: Order size in base asset.
            price: Limit price (None for market order).

        Returns:
            Self for chaining.
        """
        self._orders.append({
            "symbol": symbol,
            "side": side.upper(),
            "size": size,
            "price": price,
        })
        return self

    def execute(self, client) -> List[Any]:
        """
        Submit all orders in the batch.

        Attempts to use Orderly's batch order endpoint first.
        Falls back to sequential submission with rate limiting.

        Args:
            client: Authenticated Arthur client instance.

        Returns:
            List of Order objects or error dicts for each order.
        """
        if not self._orders:
            return []

        # Try batch endpoint first
        try:
            return self._execute_batch(client)
        except Exception as e:
            logger.debug(f"Batch endpoint unavailable ({e}), using sequential")
            return self._execute_sequential(client)

    def _execute_batch(self, client) -> List[Any]:
        """Submit via Orderly batch order endpoint."""
        batch_orders = []
        for order in self._orders:
            symbol = client._normalize_symbol(order["symbol"])
            order_type = "LIMIT" if order["price"] else "MARKET"
            entry = {
                "symbol": symbol,
                "side": order["side"],
                "order_type": order_type,
                "order_quantity": str(order["size"]),
            }
            if order["price"]:
                entry["order_price"] = str(order["price"])
            batch_orders.append(entry)

        resp = client._request(
            "POST",
            "/v1/batch-order",
            data={"orders": batch_orders},
        )

        if not resp.get("success"):
            raise Exception(resp.get("message", "Batch endpoint failed"))

        results = []
        from .client import Order
        for i, row in enumerate(resp["data"].get("rows", [])):
            if row.get("success", True):
                order_data = row
                oid = str(order_data.get("order_id", f"batch_{i}"))
                self._order_ids.append(oid)
                results.append(Order(
                    order_id=oid,
                    symbol=batch_orders[i]["symbol"],
                    side=batch_orders[i]["side"],
                    order_type=batch_orders[i]["order_type"],
                    price=self._orders[i]["price"],
                    size=self._orders[i]["size"],
                    status=order_data.get("status", "NEW"),
                    created_at=int(time.time() * 1000),
                ))
            else:
                results.append({"error": row.get("message", "Unknown"), "index": i})

        self._results = results
        return results

    def _execute_sequential(self, client) -> List[Any]:
        """Submit orders one by one with rate limiting."""
        results = []
        for order in self._orders:
            try:
                if order["price"]:
                    if order["side"] == "BUY":
                        result = client.limit_buy(
                            order["symbol"],
                            price=order["price"],
                            size=order["size"],
                        )
                    else:
                        result = client.limit_sell(
                            order["symbol"],
                            price=order["price"],
                            size=order["size"],
                        )
                else:
                    if order["side"] == "BUY":
                        result = client.buy(order["symbol"], size=order["size"])
                    else:
                        result = client.sell(order["symbol"], size=order["size"])

                self._order_ids.append(result.order_id)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "order": order})

            # Rate limiting between sequential orders
            time.sleep(0.1)

        self._results = results
        return results

    def cancel_all(self, client) -> int:
        """
        Cancel all orders that were submitted by this batch.

        Args:
            client: Authenticated Arthur client instance.

        Returns:
            Number of successfully cancelled orders.
        """
        cancelled = 0
        for i, oid in enumerate(self._order_ids):
            try:
                # Get symbol from the original order
                if i < len(self._orders):
                    symbol = self._orders[i]["symbol"]
                    if client.cancel(oid, symbol):
                        cancelled += 1
            except Exception as e:
                logger.debug(f"Failed to cancel order {oid}: {e}")
        return cancelled

    @property
    def orders(self) -> List[Dict[str, Any]]:
        """Get the list of pending orders in the batch."""
        return list(self._orders)

    @property
    def results(self) -> List[Any]:
        """Get results from the last execute() call."""
        return list(self._results)

    def clear(self):
        """Clear all orders from the batch."""
        self._orders.clear()
        self._results.clear()
        self._order_ids.clear()

    def __len__(self) -> int:
        return len(self._orders)

    def __repr__(self) -> str:
        return f"BatchOrder(orders={len(self._orders)}, executed={len(self._results)})"
