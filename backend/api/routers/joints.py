from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Depends
from backend.joints.odrive.joint import ODriveJoint
from backend.joints.moteus.joint import MoteusJoint
from backend.joints.base import Joint
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from datetime import datetime, timezone
import json

from backend.db import get_session
from backend.models import RunEvent
from backend.api.ws_manager import manager
from typing import Dict
from typing import Optional
from pydantic import BaseModel, model_validator

router = APIRouter(prefix="/joints", tags=["joints"])

# Register joints by name, each on its own CAN bus
joints: Dict[str, Joint] = {
    # ODrive on can0, node 0
    # "joint1": ODriveJoint(serial_number="385F324D3037", node_id=0),
    "joint1": MoteusJoint(node_id=1),
}

class JointConfigureBody(BaseModel):
    kp: Optional[float] = None
    ki: Optional[float] = None
    kd: Optional[float] = None
    min_pos: Optional[float] = None  # turns
    max_pos: Optional[float] = None  # turns
    save_config: Optional[bool] = None  # persist to NVM if True

    @model_validator(mode="after")
    def at_least_one(self):
        if not any([
            self.kp is not None, self.ki is not None, self.kd is not None,
            self.min_pos is not None, self.max_pos is not None,
            self.save_config is not None,
        ]):
            raise ValueError("Provide at least one field to change.")
        return self

@router.get("/index", summary="List all configured joints")
def list_joints():
    """
    Return a list of all registered joints and their metadata.
    """
    result = []
    for name, joint in joints.items():
        if isinstance(joint, ODriveJoint):
            jtype = "odrive"
        elif isinstance(joint, MoteusJoint):
            jtype = "moteus"
        else:
            jtype = joint.__class__.__name__.lower()
        initialized = getattr(joint, '_initialized', False)
        result.append({
            "id": name,
            "type": jtype,
            "initialized": initialized
        })
    return result


@router.post("/{joint_name}/move")
async def move_joint(
    joint_name: str,
    position: float,
    velocity: float = None,
    accel: float = None,
    hold: bool = True,
    run_id: int | None = None,
    request: Request = None,
    session: AsyncSession = Depends(get_session),
):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    cmd_id = str(uuid4())

    # Quick readiness probe
    try:
        await joint.status()
    except Exception as e:
        # Tell UI immediately
        await manager.broadcast(joint_name, json.dumps({
            "type": "cmd_ack",
            "joint_id": joint_name,
            "cmd_id": cmd_id,
            "accepted": False,
            "run_id": run_id,
            "reason": "joint_offline",
        }))
        raise HTTPException(status_code=503, detail="Joint is offline; try again when power/transport is available")

    # Only if online: (optionally) log event + enqueue target + ack(true) + send command
    # Insert a RunEvent ONLY when recording (run_id present); schema has NOT NULL on run_events.run_id
    if run_id is not None:
        evt = RunEvent(
            run_id=run_id,
            joint_id=joint_name,
            event_type="move_requested",
            payload={"position": position, "velocity": velocity, "accel": accel, "hold": hold},
            ts=datetime.now(timezone.utc),
        )
        session.add(evt)
        await session.commit()

    ingestor = request.app.state.ingestor
    await ingestor.enqueue({
        "ts": datetime.now(timezone.utc),
        "joint_id": joint_name,
        "run_id": run_id,
        "position": None,
        "velocity": None,
        "accel": None,
        "torque": None,
        "supply_v": None,
        "motor_temp": None,
        "controller_temp": None,
        "mode": None,
        "fault_code": None,
        "error_flags": None,
        "target_position": position,
        "target_velocity": velocity,
        "target_accel": accel,
        "target_torque": None,
    })

    await manager.broadcast(joint_name, json.dumps({
        "type": "cmd_ack",
        "joint_id": joint_name,
        "cmd_id": cmd_id,
        "accepted": True,
        "run_id": run_id,
        "cmd": {"position": position, "velocity": velocity, "accel": accel, "hold": hold},
    }))

    result = await joint.move(position, velocity, accel, hold, cmd_id=cmd_id, run_id=run_id)
    return {"ok": True, "cmd_id": cmd_id, **result}

@router.post("/{joint_name}/stop")
async def stop_joint(joint_name: str):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    # <<< await here too
    await joint.stop()
    return {"status": "stopped"}

@router.get("/{joint_name}/status")
async def status_joint(joint_name: str):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    return await joint.status(include_control=True)

@router.post("/arm-all")
async def arm_all():
    results = {}
    for name, joint in joints.items():
        try:
            if not getattr(joint, "_initialized", False):
                joint.initialize()
                setattr(joint, "_initialized", True)
            results[name] = {"status": "armed"}
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)}
    return results

@router.post("/disarm-all")
async def disarm_all():
    results = {}
    for name, joint in joints.items():
        try:
            # <<< await disarm
            await joint.disarm()
            setattr(joint, "_initialized", False)
            results[name] = {"status": "disarmed"}
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)}
    return results

@router.post("/{joint_name}/calibrate")
async def calibrate_joint(
    joint_name: str,
    state: int = 3,
    save_config: bool = False
):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    if getattr(joint, "_initialized", False):
        await joint.disarm()
        setattr(joint, "_initialized", False)

    try:
        # already awaited here in your code
        return await joint.calibrate(state=state, save_config=save_config)
    except Exception as e:
        raise HTTPException(500, str(e))



@router.post("/{joint_name}/configure", operation_id="configureJoint")
async def configure_joint(joint_name: str, body: JointConfigureBody):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    # Only pass fields the client actually sent
    params = body.model_dump(exclude_unset=True)

    try:
        # Your MoteusJoint.configure should accept kp/ki/kd/min_pos/max_pos/save_config
        return await joint.configure(**params)
    except Exception as e:
        raise HTTPException(500, str(e))