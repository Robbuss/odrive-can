from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from backend.can_bus import CANBus
from backend.joints.odrive.transport import ODriveCAN
from backend.joints.odrive.joint import ODriveJoint
from backend.joints.moteus.transport import MoteusBus
from backend.joints.moteus.joint import MoteusJoint
from backend.joints.base import Joint

from typing import Dict

router = APIRouter(prefix="/joints", tags=["joints"])

# Initialize two separate CAN bus instances
odrive_bus = CANBus(iface="can0")
moteus_bus = CANBus(iface="can1")

# Register joints by name, each on its own CAN bus
joints: Dict[str, Joint] = {
    # ODrive on can0, node 0
    "joint1": ODriveJoint(ODriveCAN(iface="can0", node=0)),
    "joint2": MoteusJoint(node_id=1),
}

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
async def move_joint(joint_name: str,
                     position: float,
                     velocity: float = None,
                     accel: float = None,
                     hold: bool = True):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")
    return await joint.move(position, velocity, accel, hold)

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
    return await joint.status()

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

@router.post("/{joint_name}/configure")
async def configure_joint(
    joint_name: str,
    save_config: bool = Query(False, description="If true, save to NVM & reboot")
):
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    try:
        return await joint.configure(save_config=save_config)
    except Exception as e:
        raise HTTPException(500, str(e))