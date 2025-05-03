from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.can_bus import CANBus
from backend.odrive.can_simple import ODriveCAN
from backend.joints.odrive import ODriveJoint

router = APIRouter(prefix="/joints", tags=["joints"])

# shared CAN bus
can_bus = CANBus(iface="can0")
# joint registry
joints = {
    "joint1": ODriveJoint(ODriveCAN(iface="can0", node=0)),
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