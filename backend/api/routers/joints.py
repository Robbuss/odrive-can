from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from backend.can_bus import CANBus
from backend.odrive.can_simple import ODriveCAN
from backend.calibration.odrive_calibrator import ODriveCalibrator
from backend.joints.odrive import ODriveJoint

from pydantic import BaseModel
from typing import Any, Dict, Optional
from pathlib import Path
import json

from backend.configurator.odrive_configurator import ODriveConfigurator

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

class ConfigRequest(BaseModel):
    endpoint_data: Dict[str, Any]
    config:        Dict[str, Any]
    save_config:   bool = False


# Base path to your configurator folder
BASE_BACKEND = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR   = BASE_BACKEND / "configurator"

@router.post("/{joint_name}/config")
async def configure_joint(
    joint_name: str,
    endpoints_file: str = Query(..., description="Name of flat_endpoints JSON file in backend/configurator"),
    config_file: Optional[str] = Query(None, description="Name of your config JSON file in backend/configurator"),
    save_config: bool = Query(False, description="If true, save to NVM and reboot")
):
    """
    Restore a set of endpoint values over CAN:
    - endpoints_file: e.g. 'flat_endpoints.json'
    - config_file:    e.g. 'my_config.json' (optional)
    - save_config:    whether to write to NVM & reboot
    """
    joint = joints.get(joint_name)
    if not joint:
        raise HTTPException(404, "Unknown joint")

    # disarm if already armed
    if getattr(joint, "_initialized", False):
        joint.disarm()
        setattr(joint, "_initialized", False)

    # build file paths (prevent directory escape)
    if "/" in endpoints_file or "\\" in endpoints_file:
        raise HTTPException(400, "Invalid endpoints_file name")
    ep_path = CONFIG_DIR / endpoints_file
    if not ep_path.is_file():
        raise HTTPException(400, f"Endpoints file not found: {endpoints_file}")

    cfg_path = None
    if config_file:
        if "/" in config_file or "\\" in config_file:
            raise HTTPException(400, "Invalid config_file name")
        cfg_path = CONFIG_DIR / config_file
        if not cfg_path.is_file():
            raise HTTPException(400, f"Config file not found: {config_file}")

    # load JSON
    try:
        endpoints_data = json.loads(ep_path.read_text())
        config_data    = json.loads(cfg_path.read_text()) if cfg_path else {}
    except Exception as e:
        raise HTTPException(500, f"Error reading JSON: {e}")

    # invoke configurator
    configurator = ODriveConfigurator(
        can_bus      = can_bus,
        node_id      = joint.odrive.node,
        endpoint_data= endpoints_data
    )

    try:
        result = await configurator.restore(config_data, save_config)
        return result
    except Exception as e:
        raise HTTPException(500, detail=str(e))