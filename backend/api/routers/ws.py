from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, json
from datetime import datetime, timezone

from backend.api.ws_manager import manager
from backend.joints.sampler import get_last_snapshot
from backend.api.routers.joints import joints

router = APIRouter(prefix="/ws", tags=["ws"])

@router.websocket("/joint/{joint_name}")
async def ws_joint(websocket: WebSocket, joint_name: str):
    await websocket.accept()
    await manager.connect(joint_name, websocket)

    try:
        # Send last snapshot or a quick probe
        snap = get_last_snapshot(joint_name)
        if snap:
            await websocket.send_text(json.dumps(snap))
        else:
            try:
                st = await joints[joint_name].status()
                now = datetime.now(timezone.utc).isoformat()
                await websocket.send_text(json.dumps({"type": "status", "joint_id": joint_name, "online": True}))
                await websocket.send_text(json.dumps({
                    "type": "telemetry", "joint_id": joint_name, "ts": now,
                    "position": st.get("position"), "velocity": st.get("velocity"),
                    "accel": None, "torque": None, "supply_v": st.get("supply_v"),
                    "motor_temp": None, "controller_temp": None,
                    "mode": None, "fault_code": st.get("fault"), "error_flags": 0,
                    "target_position": None, "target_velocity": None,
                    "target_accel": None, "target_torque": None,
                }))
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "status", "joint_id": joint_name, "online": False, "reason": str(e)
                }))

        # Race shutdown vs client message; DRAIN task results to suppress warnings
        t_shutdown = asyncio.create_task(manager.shutdown_event.wait())
        t_recv = asyncio.create_task(websocket.receive_text())
        done, pending = await asyncio.wait({t_shutdown, t_recv}, return_when=asyncio.FIRST_COMPLETED)

        # Cancel the loser(s) and DRAIN everything
        for t in pending:
            t.cancel()
        # Drain completed tasks (consume exceptions)
        for t in done:
            try:
                t.result()
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        # Drain cancelled tasks to swallow CancelledError
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(joint_name, websocket)