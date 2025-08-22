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
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Dict, Optional, Literal, List, Any

router = APIRouter(prefix="/joints", tags=["joints"])

# Register joints by name, each on its own CAN bus
joints: Dict[str, Joint] = {
    # ODrive on can0, node 0
    # "joint1": ODriveJoint(serial_number="385F324D3037", node_id=0),
    "joint1": MoteusJoint(node_id=1),
}

class JointConfigFields(BaseModel):
    kp: Optional[float] = None
    ki: Optional[float] = None
    kd: Optional[float] = None
    min_pos: Optional[float] = None  # turns
    max_pos: Optional[float] = None  # turns

    # keep this strict so you notice typos in config keys
    model_config = ConfigDict(extra='forbid')

class JointConfigureBody(JointConfigFields):
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

class JointStatus(BaseModel):
    position: Optional[float] = None
    velocity: Optional[float] = None
    accel: Optional[float] = None
    torque: Optional[float] = None
    supply_v: Optional[float] = None
    motor_temp: Optional[float] = None
    controller_temp: Optional[float] = None
    mode: Optional[Any] = None
    fault_code: Optional[int] = None
    error_flags: Optional[Dict[str, Any]] = None
    target_position: Optional[float] = None
    target_velocity: Optional[float] = None
    target_accel: Optional[float] = None
    target_torque: Optional[float] = None
    model_config = ConfigDict(extra='allow')

class JointStatusWithConfig(JointStatus, JointConfigFields):
    # still allow driver-specific extras in the combined response
    model_config = ConfigDict(extra='allow')

class JointSummary(BaseModel):
    id: str
    type: Literal['odrive', 'moteus']
    initialized: bool

class MoveResponse(BaseModel):
    ok: bool
    cmd_id: str
    # Allow extra keys from specific joint.move(...) implementations
    model_config = ConfigDict(extra='allow')

class StopResponse(BaseModel):
    status: Literal['stopped']


class ArmDisarmResult(BaseModel):
    status: Literal['armed', 'disarmed', 'error']
    detail: Optional[str] = None

class CalibrateResponse(BaseModel):
    ok: Optional[bool] = None
    detail: Optional[str] = None

    model_config = ConfigDict(extra='allow')

@router.get("/index", summary="List all configured joints", response_model=List[JointSummary])
def list_joints() -> List[JointSummary]:
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


@router.post("/{joint_name}/move", response_model=MoveResponse)
async def move_joint(
    joint_name: str,
    position: float,
    velocity: Optional[float] = None,
    accel: Optional[float] = None,
    hold: bool = True,
    run_id: Optional[int] = None,
    request: Request = None,
    session: AsyncSession = Depends(get_session),
) -> MoveResponse:
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    cmd_id = str(uuid4())

    # Quick readiness probe
    try:
        await joint.status()
    except Exception:
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
    # Preserve existing shape: {"ok": True, "cmd_id": ..., **result}
    return {"ok": True, "cmd_id": cmd_id, **(result or {})}


@router.post("/{joint_name}/stop", response_model=StopResponse)
async def stop_joint(joint_name: str) -> StopResponse:
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    await joint.stop()
    return {"status": "stopped"}


@router.get("/{joint_name}/status", response_model=JointStatusWithConfig)
async def status_joint(joint_name: str) -> JointStatusWithConfig:
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    return await joint.status(include_control=True)


@router.post("/arm-all", response_model=Dict[str, ArmDisarmResult])
async def arm_all() -> Dict[str, ArmDisarmResult]:
    results: Dict[str, ArmDisarmResult] = {}
    for name, joint in joints.items():
        try:
            if not getattr(joint, "_initialized", False):
                joint.initialize()
                setattr(joint, "_initialized", True)
            results[name] = ArmDisarmResult(status="armed")
        except Exception as e:
            results[name] = ArmDisarmResult(status="error", detail=str(e))
    return results


@router.post("/disarm-all", response_model=Dict[str, ArmDisarmResult])
async def disarm_all() -> Dict[str, ArmDisarmResult]:
    results: Dict[str, ArmDisarmResult] = {}
    for name, joint in joints.items():
        try:
            await joint.disarm()
            setattr(joint, "_initialized", False)
            results[name] = ArmDisarmResult(status="disarmed")
        except Exception as e:
            results[name] = ArmDisarmResult(status="error", detail=str(e))
    return results


@router.post("/{joint_name}/calibrate", response_model=CalibrateResponse)
async def calibrate_joint(
    joint_name: str,
    state: int = 3,
    save_config: bool = False
) -> CalibrateResponse:
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    if getattr(joint, "_initialized", False):
        await joint.disarm()
        setattr(joint, "_initialized", False)

    try:
        return await joint.calibrate(state=state, save_config=save_config)
    except Exception as e:
        raise HTTPException(500, str(e))
    
@router.post("/{joint_name}/configure", operation_id="configureJoint", response_model=dict[Literal['ok'], bool])
async def configure_joint(joint_name: str, body: JointConfigureBody):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    # Only pass fields the client actually sent
    params = body.model_dump(exclude_unset=True)

    try:
        await joint.configure(**params)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))