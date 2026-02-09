"""
WebSocket event stream for Arthur SDK.

Provides real-time event streaming from Orderly Network WebSocket API
with auto-reconnect and event callbacks.

Requires optional dependency: pip install arthur-sdk[realtime]

Example:
    from arthur_sdk import Arthur, EventStream

    client = Arthur.from_credentials_file("creds.json")
    stream = EventStream(client)
    stream.on("fill", lambda data: print(f"Fill: {data}"))
    stream.on("position_update", lambda data: print(f"Position: {data}"))
    stream.connect()  # Blocks, or use stream.connect(background=True)
"""

import json
import time
import logging
import threading
from typing import Callable, Dict, List, Any, Optional

logger = logging.getLogger("arthur_sdk.events")

# Valid event types
EVENT_TYPES = {"fill", "order_update", "position_update", "liquidation"}


class EventStream:
    """
    WebSocket event stream wrapper for Orderly Network.

    Connects to the Orderly private WebSocket and dispatches events
    to registered callbacks. Supports auto-reconnect with exponential backoff.

    Args:
        client: Authenticated Arthur client instance.
        url: WebSocket URL override (default: Orderly mainnet WS).

    Example:
        stream = EventStream(client)
        stream.on("fill", my_fill_handler)
        stream.connect(background=True)
        # ... do other work ...
        stream.disconnect()
    """

    WS_URL = "wss://ws-private-evm.orderly.org/v2/ws/private/stream"
    WS_URL_TESTNET = "wss://testnet-ws-private-evm.orderly.org/v2/ws/private/stream"

    def __init__(self, client, url: Optional[str] = None):
        """
        Initialize EventStream.

        Args:
            client: Authenticated Arthur client instance.
            url: Custom WebSocket URL (optional).
        """
        self.client = client
        self.url = url or (
            self.WS_URL_TESTNET
            if "testnet" in client.BASE_URL
            else self.WS_URL
        )
        self._callbacks: Dict[str, List[Callable]] = {evt: [] for evt in EVENT_TYPES}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def on(self, event: str, callback: Callable) -> "EventStream":
        """
        Register a callback for an event type.

        Args:
            event: Event type - one of 'fill', 'order_update',
                   'position_update', 'liquidation'.
            callback: Function to call with event data dict.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If event type is not recognized.
        """
        if event not in EVENT_TYPES:
            raise ValueError(
                f"Unknown event type '{event}'. Valid types: {EVENT_TYPES}"
            )
        self._callbacks[event].append(callback)
        return self

    def connect(self, background: bool = False):
        """
        Connect to the WebSocket and start receiving events.

        Args:
            background: If True, run in a daemon thread and return immediately.
                       If False, block the current thread.
        """
        self._running = True
        if background:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._run_loop()

    def disconnect(self):
        """Disconnect from the WebSocket and stop receiving events."""
        self._running = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def connected(self) -> bool:
        """Whether the stream is currently running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def _run_loop(self):
        """Main reconnection loop."""
        try:
            import websockets
            _has_websockets = True
        except ImportError:
            _has_websockets = False

        if not _has_websockets:
            # Fallback: try websocket-client
            try:
                import websocket as ws_client
                self._run_loop_websocket_client(ws_client)
                return
            except ImportError:
                raise ImportError(
                    "EventStream requires 'websockets' or 'websocket-client'. "
                    "Install with: pip install arthur-sdk[realtime]"
                )

        # Use websockets with sync API via threading
        self._run_loop_websockets(websockets)

    def _run_loop_websockets(self, websockets_mod):
        """Run loop using the websockets library (sync wrapper)."""
        import asyncio

        async def _async_loop():
            while self._running:
                try:
                    account_id = self.client.account_id or ""
                    url = f"{self.url}/{account_id}"
                    async with websockets_mod.connect(url) as ws:
                        self._reconnect_delay = 1.0
                        logger.info(f"Connected to {self.url}")

                        # Authenticate
                        from .auth import generate_auth_headers
                        headers = generate_auth_headers(
                            api_key=self.client.api_key,
                            secret_key=self.client.secret_key,
                            account_id=self.client.account_id,
                            method="GET",
                            path="/v2/ws/private/stream",
                            body="",
                        )
                        auth_msg = {
                            "id": "auth",
                            "event": "auth",
                            "params": {
                                "orderly_key": self.client.api_key,
                                "sign": headers.get("orderly-signature", ""),
                                "timestamp": headers.get("orderly-timestamp", ""),
                            },
                        }
                        await ws.send(json.dumps(auth_msg))

                        # Subscribe to execution report
                        sub_msg = {
                            "id": "sub_executionreport",
                            "event": "subscribe",
                            "topic": "executionreport",
                        }
                        await ws.send(json.dumps(sub_msg))

                        # Subscribe to position
                        sub_pos = {
                            "id": "sub_position",
                            "event": "subscribe",
                            "topic": "position",
                        }
                        await ws.send(json.dumps(sub_pos))

                        while self._running:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                                self._handle_message(msg)
                            except asyncio.TimeoutError:
                                # Send ping
                                await ws.send(json.dumps({"event": "ping"}))

                except Exception as e:
                    if not self._running:
                        break
                    logger.warning(
                        f"WS disconnected: {e}. Reconnecting in {self._reconnect_delay}s"
                    )
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_async_loop())
        finally:
            loop.close()

    def _run_loop_websocket_client(self, ws_client):
        """Run loop using websocket-client library."""
        while self._running:
            try:
                account_id = self.client.account_id or ""
                url = f"{self.url}/{account_id}"
                ws = ws_client.create_connection(url, timeout=30)
                self._ws = ws
                self._reconnect_delay = 1.0
                logger.info(f"Connected to {self.url}")

                # Authenticate
                from .auth import generate_auth_headers
                headers = generate_auth_headers(
                    api_key=self.client.api_key,
                    secret_key=self.client.secret_key,
                    account_id=self.client.account_id,
                    method="GET",
                    path="/v2/ws/private/stream",
                    body="",
                )
                auth_msg = {
                    "id": "auth",
                    "event": "auth",
                    "params": {
                        "orderly_key": self.client.api_key,
                        "sign": headers.get("orderly-signature", ""),
                        "timestamp": headers.get("orderly-timestamp", ""),
                    },
                }
                ws.send(json.dumps(auth_msg))
                ws.send(json.dumps({
                    "id": "sub_executionreport",
                    "event": "subscribe",
                    "topic": "executionreport",
                }))
                ws.send(json.dumps({
                    "id": "sub_position",
                    "event": "subscribe",
                    "topic": "position",
                }))

                while self._running:
                    msg = ws.recv()
                    if msg:
                        self._handle_message(msg)

            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    f"WS disconnected: {e}. Reconnecting in {self._reconnect_delay}s"
                )
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )
            finally:
                self._ws = None

    def _handle_message(self, raw: str):
        """Parse and dispatch a WebSocket message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        topic = data.get("topic", "")
        event_data = data.get("data", data)

        # Map Orderly topics to our event types
        if topic == "executionreport":
            status = event_data.get("status", "")
            if status == "FILLED" or status == "PARTIAL_FILLED":
                self._dispatch("fill", event_data)
            self._dispatch("order_update", event_data)
        elif topic == "position":
            self._dispatch("position_update", event_data)
            # Check for liquidation
            if event_data.get("liquidation", False):
                self._dispatch("liquidation", event_data)

    def _dispatch(self, event: str, data: Any):
        """Call all registered callbacks for an event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception as e:
                logger.error(f"Error in {event} callback: {e}")

    def __repr__(self) -> str:
        return f"EventStream(url={self.url!r}, running={self._running})"
