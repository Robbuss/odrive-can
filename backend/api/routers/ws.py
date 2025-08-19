from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json, asyncio

from backend.api.ws_manager import manager
from backend.api.routers.joints import joints

router = APIRouter(prefix="/ws", tags=["ws"])

# @router.websocket("/joint/{joint_name}")
# async def joint_status_ws(websocket: WebSocket, joint_name: str):
#     # Validate joint
#     if joint_name not in joints:
#         await websocket.close(code=1008)
#         return

#     await manager.connect(joint_name, websocket)
#     # Determine update frequency (default 10 Hz)
#     try:
#         freq = float(websocket.query_params.get('freq', '10'))
#         if freq <= 0:
#             freq = 10.0
#     except ValueError:
#         freq = 10.0
#     interval = 1.0 / freq
#     last_payload = ''

#     try:
#         while True:
#             # Retrieve joint status
#             try:
#                 status = joints[joint_name].status()
#             except Exception:
#                 status = {"position": None, "running": False}

#             payload = json.dumps(status)
#             if payload != last_payload:
#                 await manager.broadcast(joint_name, payload)
#                 last_payload = payload

#             await asyncio.sleep(interval)
#     except WebSocketDisconnect:
#         manager.disconnect(joint_name, websocket)
#     except Exception:
#         await websocket.close(code=1011)


# @router.websocket("/canlog/{bus_name}")
# async def can_log_ws(websocket: WebSocket, bus_name: str):
#     """
#     Stream every raw CAN frame as JSON. Select bus via bus_name ("odrive" or "moteus").
#     JSON format: { ts: float, id: '0x123', data: 'deadbeef' }
#     """
#     # Accept connection
#     await websocket.accept()
#     loop = asyncio.get_event_loop()

#     try:
#         while True:
#             # Blocking recv in thread pool
#             msg = None
#             if not msg:
#                 continue
#             await websocket.send_json({
#                 "ts":   msg.timestamp,
#                 "id":   hex(msg.arbitration_id),
#                 "data": msg.data.hex()
#             })
#     except WebSocketDisconnect:
#         return
#     except Exception:
#         await websocket.close(code=1011)