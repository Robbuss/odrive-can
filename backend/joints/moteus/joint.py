import math
import logging
import moteus
from backend.joints.base import Joint
from .transport import MoteusBus
from moteus import Fdcanusb, Controller
from backend.joints.moteus.calibrator import MoteusCalibrator
import asyncio

logger = logging.getLogger(__name__)

class MoteusJoint(Joint):
    """
    Async Joint implementation for a Moteus R4.11 controller over CAN.
    """
    def __init__(self, node_id: int = 0):
        super().__init__()
        qr = moteus.QueryResolution()
        qr.mode     = moteus.INT8
        qr.position = moteus.F32
        self.node_id = node_id
        self._ctrl = moteus.Controller(id=node_id, query_resolution=qr)
        self._running = False

    def initialize(self) -> None:
        """Open the underlying bus/controller if not already open."""

    async def move(
        self,
        position: float,
        velocity: float = None,
        accel: float = None,
        hold: bool = True,
    ) -> dict:
        """
        Move to an absolute `position` (turns), with optional
        `velocity` (turns/s), `accel` (turns/s²), and
        `hold` (keep holding until explicitly stopped).
        """
        print(f"Moving joint {self.node_id} to position {position}, velocity {velocity}, accel {accel}, hold {hold}")
        # 1) Stop any prior motion
        await self._ctrl.set_stop()
        await asyncio.sleep(0.05)

        # 2) Resynchronize capture
        await self._ctrl.set_recapture_position_velocity()

        # 3) Read current position
        status = await self._ctrl.query()

        # 4) Build and send the absolute-position command
        result = await self._ctrl.set_position_wait_complete(
            position=position,
            velocity=math.nan,
            velocity_limit=velocity if velocity is not None else math.nan,
            accel_limit=accel if accel is not None else math.nan,
            query=True,
        )

        return {
            "target_turns":   position,
            "start_turns":    status.values[moteus.Register.POSITION],
            "end_turns":      result.values[moteus.Register.POSITION],
            "requested_vel":  velocity,
            "requested_acc":  accel,
        }   
        
    async def stop(self) -> None:
        """Stop movement (brake)."""
        try:
            await self._ctrl.set_stop()
        finally:
            self._running = False

    async def status(self) -> dict:
        """Read and return current status."""
        try:
            status = await self._ctrl.query()
        except Exception:
            logger.exception("Status query failed")
            raise

        turns = status.values[moteus.Register.POSITION] / (2 * math.pi)
        vel = status.values[moteus.Register.VELOCITY] / (2 * math.pi)
        voltage = status.values[moteus.Register.V_BUS]
        return {
            'position': turns,
            'velocity': vel,
            'voltage': voltage,
            'running': self._running,
        }

    async def disarm(self) -> None:
        """Disarm the motor and shutdown bus."""
        await self.stop()
        self._ctrl.shutdown()
        self._running = False

    async def calibrate(self, *args, **kwargs) -> dict:
        """
        Perform a calibration sequence on the Moteus controller.
        """
        self.initialize()
        calibrator = MoteusCalibrator(self._ctrl, node_id=self.node_id)
        result = await calibrator.run()
        self._running = False
        return result

    async def configure(self, *args, **kwargs) -> dict:
        """
        Moteus has no config-restore by default.
        """
        return {'status': 'n/a'}
