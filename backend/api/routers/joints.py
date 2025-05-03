from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.can_bus import CANBus
from backend.odrive.can_simple import ODriveCAN
from backend.joints.odrive import ODriveJoint

router = APIRouter(prefix="/joints", tags=["joints"])

# Shared CAN bus instance
can_bus = CANBus(iface="can0")

# Register joints by name
joints = {
    "joint1": ODriveJoint(ODriveCAN(iface="can0", node=0)),
    # Add other Joint implementations here
}

@router.post("/{joint_name}/move")
async def move_joint(joint_name: str, delta: float, freq: float = 100.0):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    if not getattr(joint, '_initialized', False):
        joint.initialize()
        setattr(joint, '_initialized', True)
    return joint.move(delta, freq)

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