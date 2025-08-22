import asyncio, json, random
from datetime import datetime, timezone
from typing import Any, Optional

from backend.api.ws_manager import manager

_last_by_joint: dict[str, dict] = {}

def get_last_snapshot(joint_name: str) -> Optional[dict]:
    return _last_by_joint.get(joint_name)

async def run_joint_sampler(
    joint_name: str,
    joint_obj: Any,
    ingestor: Any,
    hz: int = 100,
    eps_pos: float = 0.005,
    eps_vel: float = 0.01,
    settle_ticks: int = 3,
):
    period = 1.0 / max(1, hz)
    ok_count = 0
    offline = False
    backoff = 0.5
    backoff_max = 5.0

    loop = asyncio.get_running_loop()

    while True:
        t0 = loop.time()
        try:
            st = await joint_obj.status()  # raises when transport missing

            # Transition: offline -> online
            if offline:
                offline = False
                backoff = 0.5
                await manager.broadcast(joint_name, json.dumps({
                    "type": "status",
                    "joint_id": joint_name,
                    "online": True,
                }))

            now = datetime.now(timezone.utc)
            row = {
                "ts": now,
                "joint_id": joint_name,
                "run_id": None,
                "position": st.get("position"),
                "velocity": st.get("velocity"),
                "accel": None,
                "torque": None,
                "supply_v": st.get("supply_v"),
                "motor_temp": None,
                "controller_temp": None,
                "mode": None,
                "fault_code": None,
                "error_flags": None,
                "target_position": None,
                "target_velocity": None,
                "target_accel": None,
                "target_torque": None,
            }

            # Persist only when online
            await ingestor.enqueue(row)

            # Broadcast telemetry
            ws_msg = {"type": "telemetry", **row, "ts": now.isoformat()}
            _last_by_joint[joint_name] = ws_msg
            await manager.broadcast(joint_name, json.dumps(ws_msg))

            # Done detection
            current = joint_obj.get_current_cmd() if hasattr(joint_obj, "get_current_cmd") else None
            if current and row["position"] is not None and row["velocity"] is not None:
                pos_err = abs(row["position"] - current["target"])
                vel_mag = abs(row["velocity"])
                if pos_err < eps_pos and vel_mag < eps_vel:
                    ok_count += 1
                    if ok_count >= settle_ticks:
                        await manager.broadcast(joint_name, json.dumps({
                            "type": "cmd_done",
                            "joint_id": joint_name,
                            "cmd_id": current.get("cmd_id"),
                            "ok": True,
                        }))
                        joint_obj.clear_current_cmd()
                        ok_count = 0
                else:
                    ok_count = 0

            # Pace at hz while online
            dt = loop.time() - t0
            await asyncio.sleep(max(0.0, period - dt))

        except asyncio.CancelledError:
            raise

        except Exception as e:
            # Transition: online -> offline
            if not offline:
                offline = True
                ok_count = 0
                await manager.broadcast(joint_name, json.dumps({
                    "type": "status",
                    "joint_id": joint_name,
                    "online": False,
                    "reason": str(e),
                }))
            # Back off retries; add tiny jitter to avoid thundering herd
            jitter = random.uniform(-0.05, 0.05) * backoff
            await asyncio.sleep(max(0.25, min(backoff_max, backoff + jitter)))
            backoff = min(backoff_max, backoff * 1.5)
            # loop continues; no DB insert or telemetry while offline