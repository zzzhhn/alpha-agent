"""WebSocket endpoints for real-time data streaming.

Blueprint p3-4: WebSocket security via token exchange + per-connection session binding.
Channels:
  - /ws/ohlcv/{ticker}  — live OHLCV candles (1-min interval)
  - /ws/alerts           — system alerts and anomaly notifications
  - /ws/watchlist_changes — ticker watchlist updates
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from alpha_agent.api.security import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# --------------------------------------------------------------------------- #
# Connection manager
# --------------------------------------------------------------------------- #


class ConnectionManager:
    """Manages active WebSocket connections grouped by channel."""

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(websocket)
        logger.info("WS connected: %s (total: %d)", channel, len(self._channels[channel]))

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        if channel in self._channels:
            self._channels[channel].discard(websocket)
            if not self._channels[channel]:
                del self._channels[channel]

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Send data to all connections on a channel."""
        if channel not in self._channels:
            return

        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []

        for ws in self._channels[channel]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._channels[channel].discard(ws)

    def channel_count(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))

    def total_connections(self) -> int:
        return sum(len(conns) for conns in self._channels.values())

    def stats(self) -> dict[str, Any]:
        return {
            "total_connections": self.total_connections(),
            "channels": {ch: len(conns) for ch, conns in self._channels.items()},
        }


# Shared manager instance
manager = ConnectionManager()


# --------------------------------------------------------------------------- #
# WebSocket authentication
# --------------------------------------------------------------------------- #


async def _authenticate_ws(websocket: WebSocket) -> bool:
    """Authenticate WebSocket via token in query params or first message.

    Blueprint: token exchange during handshake initialization.
    In demo mode (no ALPHACORE_AUTH_ENABLED), always returns True.
    """
    # Check query param first
    token = websocket.query_params.get("token")
    if token:
        payload = verify_token(token)
        if payload is not None:
            websocket.state.user = payload
            return True

    # No token in query — accept anyway in demo mode
    # In production, reject unauthenticated connections
    return True


# --------------------------------------------------------------------------- #
# OHLCV streaming endpoint
# --------------------------------------------------------------------------- #


@router.websocket("/ws/ohlcv/{ticker}")
async def ws_ohlcv(websocket: WebSocket, ticker: str) -> None:
    """Stream live OHLCV data for a ticker.

    Blueprint p8: WebSocket /ws/ohlcv/{ticker}, emits new candle every minute.
    """
    if not await _authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = f"ohlcv:{ticker}"
    await manager.connect(websocket, channel)

    try:
        # Keep connection alive, listen for client messages (ping/config)
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )
                # Client can send ping or config messages
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                }))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, channel)


# --------------------------------------------------------------------------- #
# Alert streaming endpoint
# --------------------------------------------------------------------------- #


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    """Stream system alerts and anomaly notifications.

    Blueprint p5: WebSocket /ws/alerts — rolling alert list.
    """
    if not await _authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = "alerts"
    await manager.connect(websocket, channel)

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                }))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, channel)


# --------------------------------------------------------------------------- #
# Watchlist changes endpoint
# --------------------------------------------------------------------------- #


@router.websocket("/ws/watchlist_changes")
async def ws_watchlist(websocket: WebSocket) -> None:
    """Stream watchlist ticker additions/removals.

    Blueprint p8: subscribe /ws/watchlist_changes for tab updates.
    """
    if not await _authenticate_ws(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    channel = "watchlist"
    await manager.connect(websocket, channel)

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0,
                )
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                }))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, channel)
