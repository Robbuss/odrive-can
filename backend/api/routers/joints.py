from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from backend.can_bus import CANBus
from backend.joints.odrive.transport import ODriveCAN
from backend.joints.odrive.joint import ODriveJoint

from typing import Any, Dict


router = APIRouter(prefix="/joints", tags=["joints"])

# Shared CAN bus instance
can_bus = CANBus(iface="can0")

# Register joints by name
joints = {
    "joint1": ODriveJoint(ODriveCAN(iface="can0", node=0)),
    # Add other Joint implementations here
}

@router.post("/{joint_name}/move")
async def move_joint(joint_name: str, delta: float, speed: float = None):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    if not getattr(joint, '_initialized', False):
        joint.initialize()
        setattr(joint, '_initialized', True)
    return joint.move(delta, speed)

@router.post("/{joint_name}/stop")
async def stop_joint(joint_name: str):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    joint.stop()
    return {"status": "stopped"}

@router.get("/{joint_name}/status")
async def status_joint(joint_name: str):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    return joint.status()

@router.post("/arm-all")
async def arm_all():
    """Initialize (arm) every registered joint."""
    results = {}
    for name, joint in joints.items():
        try:
            if not getattr(joint, '_initialized', False):
                joint.initialize()
                setattr(joint, '_initialized', True)
            results[name] = {"status": "armed"}
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)}
    return results

@router.post("/disarm-all")
async def disarm_all():
    results = {}
    for name, joint in joints.items():
        try:
            joint.disarm()
            # allow next arm-all to actually re-initialize
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
    """
    Run calibration on the given joint.

    Query params:
      - state: AxisState code (default 3 = FULL_CALIBRATION_SEQUENCE)
      - save_config: if true, save to NVM & reboot
    """
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    # If previously armed, disarm to reset bus
    if getattr(joint, "_initialized", False):
        joint.disarm()
        setattr(joint, "_initialized", False)

    try:
        result = await joint.calibrate(state=state, save_config=save_config)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{joint_name}/configure")
async def configure_joint(
    joint_name: str,
    save_config: bool = Query(False, description="If true, save to NVM & reboot")
):
    """
    Trigger the on-disk config/config.json → flat_endpoints.json restore flow.
    """
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    try:
        result = await joint.configure(save_config=save_config)
        return result
    except Exception as e:
        raise HTTPException(500, detail=str(e))
