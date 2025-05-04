from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json, asyncio

from backend.api.ws_manager import manager
from backend.api.routers.joints import joints, can_bus

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/joint/{joint_name}")
async def joint_status_ws(websocket: WebSocket, joint_name: str):
    # Validate joint name
    if joint_name not in joints:
        return await websocket.close(code=1008)

    # Register this connection
    await manager.connect(joint_name, websocket)

    # Read optional ?freq=Hz query param (default 10 Hz)
    try:
        freq = float(websocket.query_params.get("freq", "10"))
        if freq <= 0:
            freq = 10.0
    except ValueError:
        freq = 10.0
    interval = 1.0 / freq

    last_payload = ""
    try:
        while True:
            # Attempt to get status, fallback if it fails
            try:
                status = joints[joint_name].status()
            except Exception:
                status = {"position": None, "running": False}

            payload = json.dumps(status)
            if payload != last_payload:
                await manager.broadcast(joint_name, payload)
                last_payload = payload

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        manager.disconnect(joint_name, websocket)
    except Exception:
        await websocket.close(code=1011)


@router.websocket("/canlog")
async def can_log_ws(websocket: WebSocket):
    """
    Stream every raw CAN frame as JSON:
      { ts: float, id: '0x123', data: 'deadbeef' }
    """
    channel = "canlog"
    # Register this connection under the 'canlog' channel
    await manager.connect(channel, websocket)

    loop = asyncio.get_event_loop()
    # Ensure the CAN bus is open
    if not can_bus.bus:
        can_bus.open()

    try:
        while True:
            # Block in a thread to await a CAN frame
            msg = await loop.run_in_executor(None, lambda: can_bus.bus.recv(timeout=1.0))
            if not msg:
                continue

            entry = {
                "ts": msg.timestamp,
                "id": hex(msg.arbitration_id),
                "data": msg.data.hex()
            }
            # Broadcast to all clients listening on 'canlog'
            await manager.broadcast(channel, json.dumps(entry))
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)
    except Exception:
        await websocket.close(code=1011)