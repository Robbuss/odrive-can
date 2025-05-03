from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List

class ConnectionManager:
    """
    Manages WebSocket connections per joint.
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, joint_name: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(joint_name, []).append(websocket)

    def disconnect(self, joint_name: str, websocket: WebSocket):
        conns = self.active_connections.get(joint_name, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active_connections.pop(joint_name, None)

    async def broadcast(self, joint_name: str, message: str):
        for ws in self.active_connections.get(joint_name, []):
            await ws.send_text(message)

# single shared manager
manager = ConnectionManager()