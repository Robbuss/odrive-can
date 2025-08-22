from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from datetime import datetime, timezone

from backend.api.ws_manager import manager
from backend.joints.sampler import get_last_snapshot
from backend.api.routers.joints import joints
from backend.util.json_fast import fast_dumps 

router = APIRouter(prefix="/ws", tags=["ws"])

@router.websocket("/joint/{joint_name}")
async def ws_joint(websocket: WebSocket, joint_name: str):
    # Accept first, then register with manager
    await websocket.accept()
    await manager.connect(joint_name, websocket)

    try:
        # Send last snapshot if we have it; else do a quick status probe
        snap = get_last_snapshot(joint_name)
        if snap:
            await websocket.send_text(fast_dumps(snap))
        else:
            try:
                # Use fast path if available to avoid diag reads in the hot path
                status_fn = getattr(joints[joint_name], "status")
                st = await status_fn(include_control=False) if status_fn.__code__.co_argcount >= 2 else await status_fn()
                now = datetime.now(timezone.utc).isoformat()

                await websocket.send_text(fast_dumps({
                    "type": "status", "joint_id": joint_name, "online": True
                }))
                await websocket.send_text(fast_dumps({
                    "type": "telemetry", "joint_id": joint_name, "ts": now,
                    "position": st.get("position"), "velocity": st.get("velocity"),
                    "accel": None, "torque": None, "supply_v": st.get("supply_v"),
                    "motor_temp": None, "controller_temp": None,
                    "mode": None, "fault_code": st.get("fault"), "error_flags": 0,
                    "target_position": None, "target_velocity": None,
                    "target_accel": None, "target_torque": None,
                }))
            except Exception as e:
                await websocket.send_text(fast_dumps({
                    "type": "status", "joint_id": joint_name, "online": False, "reason": str(e)
                }))

        # Wait until either:
        #  - the backend is shutting down (hot reload), or
        #  - the client sends anything (we just treat it as a keepalive)
        t_shutdown = asyncio.create_task(manager.shutdown_event.wait())
        t_recv = asyncio.create_task(websocket.receive_text())
        done, pending = await asyncio.wait({t_shutdown, t_recv}, return_when=asyncio.FIRST_COMPLETED)

        # Cancel the loser(s) and drain all tasks to suppress warnings
        for t in pending:
            t.cancel()
        for t in done:
            try:
                t.result()
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        # client closed; normal path
        pass
    except Exception:
        # swallow unexpected WS exceptions; manager cleanup below
        pass
    finally:
        manager.disconnect(joint_name, websocket)