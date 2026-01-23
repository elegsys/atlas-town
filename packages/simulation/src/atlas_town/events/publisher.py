"""WebSocket event publisher for real-time frontend updates.

The publisher maintains connections to frontend clients and broadcasts
simulation events as they occur. It supports:
- Multiple concurrent client connections
- Automatic reconnection handling
- Event filtering by type or organization
- Buffering of recent events for late-joining clients
"""

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
import websockets
from websockets.asyncio.server import Server, ServerConnection

from atlas_town.config import get_settings
from atlas_town.events.types import EventType, SimulationEvent

logger = structlog.get_logger(__name__)


@dataclass
class ClientConnection:
    """Represents a connected WebSocket client."""

    websocket: ServerConnection
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    subscribed_events: set[EventType] = field(default_factory=set)
    subscribed_orgs: set[UUID] = field(default_factory=set)
    client_id: str = ""

    def __post_init__(self) -> None:
        # Generate client ID from remote address
        if not self.client_id and self.websocket.remote_address:
            addr = self.websocket.remote_address
            self.client_id = f"{addr[0]}:{addr[1]}" if isinstance(addr, tuple) else str(addr)

    def __hash__(self) -> int:
        """Make hashable for use in sets (required for websockets v15+)."""
        return hash(id(self.websocket))

    def __eq__(self, other: object) -> bool:
        """Equality based on websocket identity."""
        if not isinstance(other, ClientConnection):
            return False
        return self.websocket is other.websocket


class EventPublisher:
    """WebSocket server for publishing simulation events.

    Usage:
        publisher = EventPublisher()
        await publisher.start()

        # Publish events
        publisher.publish(some_event)

        # Shutdown
        await publisher.stop()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        buffer_size: int = 100,
    ):
        settings = get_settings()
        self._host = host or settings.ws_host
        self._port = port or settings.ws_port
        self._buffer_size = buffer_size

        self._server: Server | None = None
        self._clients: set[ClientConnection] = set()
        self._event_buffer: deque[SimulationEvent] = deque(maxlen=buffer_size)
        self._is_running = False

        # Event hooks for external processing
        self._event_hooks: list[Callable[[SimulationEvent], None]] = []

        self._logger = logger.bind(component="event_publisher")

    @property
    def is_running(self) -> bool:
        """Check if the publisher is running."""
        return self._is_running

    @property
    def client_count(self) -> int:
        """Get the number of connected clients."""
        return len(self._clients)

    @property
    def recent_events(self) -> list[SimulationEvent]:
        """Get recently published events."""
        return list(self._event_buffer)

    def add_event_hook(self, hook: Callable[[SimulationEvent], None]) -> None:
        """Add a hook to be called for every event.

        Hooks are called synchronously before broadcasting.

        Args:
            hook: Function that receives each event.
        """
        self._event_hooks.append(hook)

    def remove_event_hook(self, hook: Callable[[SimulationEvent], None]) -> None:
        """Remove an event hook."""
        if hook in self._event_hooks:
            self._event_hooks.remove(hook)

    async def start(self) -> None:
        """Start the WebSocket server."""
        if self._is_running:
            self._logger.warning("publisher_already_running")
            return

        self._logger.info("starting_publisher", host=self._host, port=self._port)

        self._server = await websockets.serve(
            self._handle_client,
            self._host,
            self._port,
            ping_interval=30,
            ping_timeout=10,
        )

        self._is_running = True
        self._logger.info("publisher_started", address=f"ws://{self._host}:{self._port}")

    async def stop(self) -> None:
        """Stop the WebSocket server and disconnect all clients."""
        if not self._is_running:
            return

        self._logger.info("stopping_publisher", client_count=len(self._clients))

        # Close all client connections
        close_tasks = []
        for client in list(self._clients):
            close_tasks.append(client.websocket.close(1001, "Server shutting down"))

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self._clients.clear()

        # Stop the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._is_running = False
        self._logger.info("publisher_stopped")

    async def _handle_client(self, websocket: ServerConnection) -> None:
        """Handle a new client connection."""
        client = ClientConnection(websocket=websocket)
        self._clients.add(client)

        self._logger.info("client_connected", client_id=client.client_id)

        # Send recent events to new client
        await self._send_event_history(client)

        try:
            async for message in websocket:
                await self._handle_message(client, message)
        except websockets.ConnectionClosed as e:
            self._logger.info(
                "client_disconnected",
                client_id=client.client_id,
                code=e.code,
                reason=e.reason,
            )
        except Exception as e:
            self._logger.error("client_error", client_id=client.client_id, error=str(e))
        finally:
            self._clients.discard(client)

    async def _handle_message(self, client: ClientConnection, message: str | bytes) -> None:
        """Handle an incoming message from a client.

        Supported message types:
        - subscribe: Subscribe to specific event types or orgs
        - unsubscribe: Unsubscribe from event types or orgs
        - ping: Health check
        """
        try:
            if isinstance(message, bytes):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError:
                    self._logger.warning("invalid_message_encoding", client_id=client.client_id)
                    return

            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "subscribe":
                await self._handle_subscribe(client, data)
            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(client, data)
            elif msg_type == "ping":
                await client.websocket.send(json.dumps({"type": "pong"}))
            else:
                self._logger.warning(
                    "unknown_message_type",
                    client_id=client.client_id,
                    msg_type=msg_type,
                )

        except json.JSONDecodeError:
            self._logger.warning("invalid_json", client_id=client.client_id)
        except Exception as e:
            self._logger.error("message_handling_error", error=str(e))

    async def _handle_subscribe(
        self, client: ClientConnection, data: dict[str, Any]
    ) -> None:
        """Handle subscription requests."""
        # Subscribe to event types
        event_types = data.get("event_types", [])
        for et in event_types:
            with contextlib.suppress(ValueError):
                client.subscribed_events.add(EventType(et))

        # Subscribe to specific organizations
        org_ids = data.get("org_ids", [])
        for oid in org_ids:
            with contextlib.suppress(ValueError):
                client.subscribed_orgs.add(UUID(oid))

        self._logger.debug(
            "client_subscribed",
            client_id=client.client_id,
            events=len(client.subscribed_events),
            orgs=len(client.subscribed_orgs),
        )

        # Send confirmation
        await client.websocket.send(
            json.dumps(
                {
                    "type": "subscribed",
                    "event_types": [et.value for et in client.subscribed_events],
                    "org_ids": [str(oid) for oid in client.subscribed_orgs],
                }
            )
        )

    async def _handle_unsubscribe(
        self, client: ClientConnection, data: dict[str, Any]
    ) -> None:
        """Handle unsubscription requests."""
        event_types = data.get("event_types", [])
        for et in event_types:
            with contextlib.suppress(ValueError):
                client.subscribed_events.discard(EventType(et))

        org_ids = data.get("org_ids", [])
        for oid in org_ids:
            with contextlib.suppress(ValueError):
                client.subscribed_orgs.discard(UUID(oid))

    async def _send_event_history(self, client: ClientConnection) -> None:
        """Send recent events to a newly connected client."""
        if not self._event_buffer:
            return

        history = {
            "type": "event_history",
            "events": [event.to_dict() for event in self._event_buffer],
        }
        await client.websocket.send(json.dumps(history))

    def _should_send_to_client(
        self, client: ClientConnection, event: SimulationEvent
    ) -> bool:
        """Check if an event should be sent to a specific client.

        If the client has no subscriptions, they receive all events.
        Otherwise, check event type and org filters.
        """
        # No filters = receive everything
        if not client.subscribed_events and not client.subscribed_orgs:
            return True

        # Check event type filter
        if client.subscribed_events and event.event_type not in client.subscribed_events:
            return False

        # Check org filter for events that have org_id
        if client.subscribed_orgs:
            event_org_id = getattr(event, "org_id", None)
            if event_org_id and event_org_id not in client.subscribed_orgs:
                return False

        return True

    def publish(self, event: SimulationEvent) -> None:
        """Publish an event to all subscribed clients.

        This is a non-blocking call. The event is queued for
        async delivery to clients.

        Args:
            event: The event to publish.
        """
        # Add to buffer
        self._event_buffer.append(event)

        # Call hooks
        for hook in self._event_hooks:
            try:
                hook(event)
            except Exception as e:
                self._logger.error("event_hook_error", error=str(e))

        # Schedule async broadcast
        if self._is_running:
            asyncio.create_task(self._broadcast(event))

    async def _broadcast(self, event: SimulationEvent) -> None:
        """Broadcast an event to all subscribed clients."""
        if not self._clients:
            return

        message = json.dumps(event.to_dict())

        # Send to all matching clients
        tasks = []
        for client in list(self._clients):
            if self._should_send_to_client(client, event):
                tasks.append(self._safe_send(client, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, client: ClientConnection, message: str) -> None:
        """Send a message to a client, handling errors."""
        try:
            await client.websocket.send(message)
        except websockets.ConnectionClosed:
            self._clients.discard(client)
        except Exception as e:
            self._logger.error(
                "send_error",
                client_id=client.client_id,
                error=str(e),
            )

    async def broadcast_all(self, event: SimulationEvent) -> None:
        """Broadcast an event and wait for completion.

        Unlike publish(), this waits for the broadcast to complete.
        """
        self._event_buffer.append(event)

        for hook in self._event_hooks:
            try:
                hook(event)
            except Exception as e:
                self._logger.error("event_hook_error", error=str(e))

        await self._broadcast(event)

    def get_status(self) -> dict[str, Any]:
        """Get publisher status information."""
        return {
            "is_running": self._is_running,
            "host": self._host,
            "port": self._port,
            "client_count": len(self._clients),
            "buffer_size": len(self._event_buffer),
            "clients": [
                {
                    "id": c.client_id,
                    "connected_at": c.connected_at.isoformat(),
                    "subscribed_events": len(c.subscribed_events),
                    "subscribed_orgs": len(c.subscribed_orgs),
                }
                for c in self._clients
            ],
        }


# Global publisher instance for convenience
_publisher: EventPublisher | None = None


def get_publisher() -> EventPublisher:
    """Get or create the global event publisher instance."""
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher


async def start_publisher() -> EventPublisher:
    """Start the global event publisher."""
    publisher = get_publisher()
    await publisher.start()
    return publisher


async def stop_publisher() -> None:
    """Stop the global event publisher."""
    global _publisher
    if _publisher:
        await _publisher.stop()
        _publisher = None
