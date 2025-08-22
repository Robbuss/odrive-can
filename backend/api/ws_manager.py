from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, Set
from starlette.websockets import WebSocket

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.shutting_down: bool = False
        self.shutdown_event: asyncio.Event = asyncio.Event()

    async def connect(self, joint_id: str, websocket: WebSocket) -> None:
        if self.shutting_down:
            return
        self.active_connections[joint_id].add(websocket)

    def disconnect(self, joint_id: str, websocket: WebSocket) -> None:
        conns = self.active_connections.get(joint_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self.active_connections.pop(joint_id, None)

    async def broadcast(self, joint_id: str, message: str) -> None:
        if self.shutting_down:
            return
        conns = list(self.active_connections.get(joint_id, ()))
        if not conns:
            return

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(joint_id, ws)

    async def shutdown(self) -> None:
        # Wake all WS handlers immediately; stop any further sends.
        self.shutting_down = True
        self.shutdown_event.set()
        # Drop references so uvicorn can tear down sockets without us awaiting handshakes.
        self.active_connections.clear()

manager = ConnectionManager()