from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Maintains active WebSocket connections keyed by service_id."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._websocket_services: dict[WebSocket, int] = {}

    async def connect(self, service_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[service_id].add(websocket)
        self._websocket_services[websocket] = service_id

    def disconnect(self, service_id: int, websocket: WebSocket) -> None:
        self._connections[service_id].discard(websocket)
        if not self._connections[service_id]:
            del self._connections[service_id]
        self._websocket_services.pop(websocket, None)

    async def broadcast_to_service(self, service_id: int, message: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in list(self._connections.get(service_id, set())):
            try:
                await websocket.send_json(message)
            except Exception as exc:
                logger.warning(
                    "Failed to broadcast to service %s: %s", service_id, exc
                )
                stale.append(websocket)

        for websocket in stale:
            bound_service_id = self._websocket_services.get(websocket, service_id)
            self.disconnect(bound_service_id, websocket)

    async def broadcast_all(self, message: dict) -> None:
        stale: list[WebSocket] = []
        for websocket in list(self._websocket_services):
            try:
                await websocket.send_json(message)
            except Exception as exc:
                logger.warning("Failed to broadcast to client: %s", exc)
                stale.append(websocket)

        for websocket in stale:
            service_id = self._websocket_services.get(websocket)
            if service_id is not None:
                self.disconnect(service_id, websocket)


manager = ConnectionManager()


@router.websocket("/{service_id}")
async def service_websocket(websocket: WebSocket, service_id: int) -> None:
    await manager.connect(service_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(service_id, websocket)
