import asyncio
import os
from typing import Any, Dict, List, Optional
from sqlalchemy import insert
from backend.db import SessionLocal
from backend.models import JointSample

FLUSH_MAX = int(os.getenv("TELEMETRY_FLUSH_MAX", 200))
FLUSH_MS  = int(os.getenv("TELEMETRY_FLUSH_MS", 200))

class TelemetryIngestor:
    def __init__(self, flush_max: int = FLUSH_MAX, flush_ms: int = FLUSH_MS):
        self.flush_max = flush_max
        self.flush_ms  = flush_ms
        self.queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        await self.queue.put(None)
        if self._task:
            await self._task

    async def enqueue(self, row: Dict[str, Any]) -> None:
        # row should match JointSample columns
        await self.queue.put(row)

    async def _flush(self, buf: List[Dict[str, Any]]) -> None:
        if not buf:
            return
        async with SessionLocal() as session:
            await session.execute(insert(JointSample), buf)
            await session.commit()

    async def _run(self) -> None:
        buf: List[Dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.flush_ms / 1000.0

        while True:
            timeout = max(0.0, deadline - loop.time())
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                item = None  # treat as time trigger

            if item is None:
                # time trigger or stop signal
                if buf:
                    await self._flush(buf)
                    buf.clear()
                if not self._running:
                    break
                deadline = loop.time() + self.flush_ms / 1000.0
                continue

            buf.append(item)
            if len(buf) >= self.flush_max:
                await self._flush(buf)
                buf.clear()
                deadline = loop.time() + self.flush_ms / 1000.0

# Singleton used by the app
ingestor = TelemetryIngestor()
