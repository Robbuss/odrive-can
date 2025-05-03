from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json, asyncio

from backend.api.ws_manager import manager
from backend.api.routers.joints import joints

router = APIRouter(prefix="/ws", tags=["ws"])

@router.websocket("/joint/{joint_name}")
async def joint_status_ws(websocket: WebSocket, joint_name: str):
    # Validate joint
    if joint_name not in joints:
        return await websocket.close(code=1008)

    # Connect socket
    await manager.connect(joint_name, websocket)

    # Determine update frequency (messages/sec) via query param, default 10Hz
    try:
        freq = float(websocket.query_params.get('freq', '10'))
        if freq <= 0:
            freq = 10.0
    except ValueError:
        freq = 10.0
    interval = 1.0 / freq

    last_payload: str = ''

    try:
        while True:
            # Retrieve joint status (or fallback)
            try:
                status = joints[joint_name].status()
            except Exception:
                status = {"position": None, "running": False}

            # Only send if payload changed
            payload = json.dumps(status)
            if payload != last_payload:
                await manager.broadcast(joint_name, payload)
                last_payload = payload

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        manager.disconnect(joint_name, websocket)
    except Exception:
        # Unexpected error
        await websocket.close(code=1011)