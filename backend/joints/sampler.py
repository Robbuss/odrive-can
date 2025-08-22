import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Optional, Dict, Tuple

from backend.util.json_fast import fast_dumps
from backend.api.ws_manager import manager
from backend.api.faults import explain_fault

_last_by_joint: Dict[str, dict] = {}
_prev_kin: Dict[str, Tuple[float, float]] = {}
_last_fault_code: Dict[str, int] = {}


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
    ws_hz: int = 30,
):
    period = 1.0 / max(1, hz)
    ws_period = 1.0 / max(1, ws_hz)

    ok_count = 0
    offline = False
    backoff = 0.5
    backoff_max = 5.0

    loop = asyncio.get_running_loop()
    next_ws_time = loop.time()
    last_ws_task: Optional[asyncio.Task] = None

    async def _send_ws(joint: str, payload: dict) -> None:
        try:
            await manager.broadcast(joint, fast_dumps(payload))
        except Exception:
            pass

    while True:
        t0 = loop.time()
        try:
            st = await joint_obj.status(include_control=False)

            if offline:
                offline = False
                backoff = 0.5
                _prev_kin.pop(joint_name, None)
                await _send_ws(joint_name, {"type": "status", "joint_id": joint_name, "online": True})

            drv1 = int(st.get("driver_fault1") or 0)
            drv2 = int(st.get("driver_fault2") or 0)
            error_flags = (drv1 & 0xFFFF) | ((drv2 & 0xFFFF) << 16)

            now_mono = loop.time()
            vel = st.get("velocity")
            accel = None
            if vel is not None:
                prev = _prev_kin.get(joint_name)
                if prev is not None:
                    prev_vel, prev_t = prev
                    dt = max(1e-6, now_mono - prev_t)
                    accel = (vel - prev_vel) / dt
                _prev_kin[joint_name] = (vel, now_mono)

            now = datetime.now(timezone.utc)
            fault_code = int(st.get("fault") or 0)

            # >>> Pull current command so we can mirror targets into each row
            current = joint_obj.get_current_cmd() if hasattr(joint_obj, "get_current_cmd") else None

            row = {
                "ts": now,
                "joint_id": joint_name,
                "run_id": (current.get("run_id") if current else None),
                "position": st.get("position"),
                "velocity": vel,
                "accel": accel,
                "torque": st.get("torque"),
                "supply_v": st.get("supply_v"),
                "motor_temp": st.get("motor_temp"),
                "controller_temp": st.get("controller_temp"),
                "mode": st.get("mode"),
                "fault_code": fault_code,
                "error_flags": error_flags,

                # >>> Fill target_* while a command is active
                "target_position": (current.get("target") if current else None),
                "target_velocity": (current.get("velocity") if current else None),
                "target_accel":    (current.get("accel") if current else None),
                "target_torque":   None,
            }

            await ingestor.enqueue(row)

            if now_mono >= next_ws_time:
                ws_msg = {"type": "telemetry", **row, "ts": now.isoformat()}
                _last_by_joint[joint_name] = ws_msg

                if last_ws_task is None or last_ws_task.done():
                    last_ws_task = asyncio.create_task(_send_ws(joint_name, ws_msg))

                next_ws_time = now_mono + ws_period

            last_fault = _last_fault_code.get(joint_name, 0)
            if fault_code != last_fault:
                _last_fault_code[joint_name] = fault_code
                if fault_code:
                    msg = explain_fault(fault_code, drv1=drv1, drv2=drv2)
                    asyncio.create_task(_send_ws(joint_name, {
                        "type": "fault",
                        "joint_id": joint_name,
                        "fault_code": fault_code,
                        "error_flags": error_flags,
                        "message": msg,
                    }))

            # Done detection
            if current and row["position"] is not None and vel is not None:
                pos_err = abs(row["position"] - current["target"])
                vel_mag = abs(vel)
                if pos_err < eps_pos and vel_mag < eps_vel:
                    ok_count += 1
                    if ok_count >= settle_ticks:
                        asyncio.create_task(_send_ws(joint_name, {
                            "type": "cmd_done",
                            "joint_id": joint_name,
                            "cmd_id": current.get("cmd_id"),
                            "ok": True,
                        }))
                        joint_obj.clear_current_cmd()
                        ok_count = 0
                else:
                    ok_count = 0

            dt = loop.time() - t0
            await asyncio.sleep(max(0.0, period - dt))

        except asyncio.CancelledError:
            break

        except Exception as e:
            if not offline:
                offline = True
                ok_count = 0
                _prev_kin.pop(joint_name, None)
                await _send_ws(joint_name, {
                    "type": "status",
                    "joint_id": joint_name,
                    "online": False,
                    "reason": str(e),
                })
            jitter = random.uniform(-0.05, 0.05) * backoff
            await asyncio.sleep(max(0.25, min(backoff_max, backoff + jitter)))
            backoff = min(backoff_max, backoff * 1.5)