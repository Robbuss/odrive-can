from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional
from starlette.websockets import WebSocket

WS_MAX_QUEUE = 32  # small buffer; drop oldest when full

@dataclass
class _Conn:
    ws: WebSocket
    q: asyncio.Queue[str]
    task: asyncio.Task

class ConnectionManager:
    def __init__(self) -> None:
        self._by_joint: Dict[str, List[_Conn]] = defaultdict(list)
        self.shutting_down: bool = False
        self.shutdown_event: asyncio.Event = asyncio.Event()

    async def _sender(self, joint_id: str, conn: _Conn):
        try:
            while not self.shutting_down:
                msg = await conn.q.get()
                if msg is None:  # sentinel
                    break
                try:
                    await conn.ws.send_text(msg)
                except Exception:
                    break
        finally:
            self._remove_conn(joint_id, conn)

    def _remove_conn(self, joint_id: str, conn: _Conn):
        conns = self._by_joint.get(joint_id)
        if not conns:
            return
        try:
            conns.remove(conn)
        except ValueError:
            pass
        if not conns:
            self._by_joint.pop(joint_id, None)

    async def connect(self, joint_id: str, websocket: WebSocket) -> None:
        if self.shutting_down:
            return
        q: asyncio.Queue[str] = asyncio.Queue(WS_MAX_QUEUE)
        conn = _Conn(ws=websocket, q=q, task=None)  # type: ignore
        task = asyncio.create_task(self._sender(joint_id, conn))
        conn.task = task  # assign after creation
        self._by_joint[joint_id].append(conn)

    def disconnect(self, joint_id: str, websocket: WebSocket) -> None:
        conns = self._by_joint.get(joint_id)
        if not conns:
            return
        target: Optional[_Conn] = None
        for c in conns:
            if c.ws is websocket:
                target = c
                break
        if not target:
            return
        try:
            target.q.put_nowait(None)  # stop sender loop
        except Exception:
            pass
        if target.task and not target.task.done():
            target.task.cancel()
        self._remove_conn(joint_id, target)

    async def broadcast(self, joint_id: str, message: str) -> None:
        """Non-blocking: enqueue to each connection's queue; drop oldest if full."""
        if self.shutting_down:
            return
        conns = self._by_joint.get(joint_id)
        if not conns:
            return
        dead: List[_Conn] = []
        for c in list(conns):
            try:
                c.q.put_nowait(message)
            except asyncio.QueueFull:
                # drop oldest, then try again
                try:
                    _ = c.q.get_nowait()
                except Exception:
                    pass
                try:
                    c.q.put_nowait(message)
                except Exception:
                    dead.append(c)
            except Exception:
                dead.append(c)
        for c in dead:
            self.disconnect(joint_id, c.ws)

    async def shutdown(self) -> None:
        self.shutting_down = True
        self.shutdown_event.set()
        for joint_id, conns in list(self._by_joint.items()):
            for c in list(conns):
                try:
                    c.q.put_nowait(None)
                except Exception:
                    pass
                if c.task and not c.task.done():
                    c.task.cancel()
            self._by_joint.pop(joint_id, None)

manager = ConnectionManager()