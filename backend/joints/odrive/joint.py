import struct, time, threading
from backend.joints.base import Joint
from backend.joints.odrive.transport import ODriveCAN, CLOSED_LOOP, IDLE, _SET_INPUT_POS
from backend.joints.odrive.calibrator import ODriveCalibrator
from backend.joints.odrive.configurator import ODriveConfigurator
class ODriveJoint(Joint):
    def __init__(self, odrive: ODriveCAN):
        self.odrive = odrive
        self._stream_thread = None
        self.calibrator = ODriveCalibrator(can_bus=self.odrive, node_id=self.odrive.node)
        self.configurator = ODriveConfigurator(can_bus = self.odrive, node_id = self.odrive.node)

    def initialize(self):
        """
        Open CAN bus and arm closed-loop.
        """
        self.odrive.initialize()

    def move(self, delta: float, freq: float = None) -> dict:
        """
        Arm (if needed), read the current position, 
        send a single SET_INPUT_POS frame, and return start/target.
        """
        # Ensure we’re armed
        if not getattr(self, "_initialized", False):
            self.initialize()
            setattr(self, "_initialized", True)

        start = self.odrive.read_turns()
        target = start + delta

        # Pack one SET_INPUT_POS message
        arb     = (self.odrive.node << 5) | _SET_INPUT_POS
        payload = struct.pack('<fhh', target, 0, 0)
        self.odrive.send(arb, payload)

        return {"start": start, "target": target}

    def status(self) -> dict:
        """Return current position and running state."""
        try:
            pos = self.odrive.read_turns(timeout=0.5)
        except RuntimeError:
            pos = None
        return {"position": pos, "running": self.odrive.running}

    def stop(self):
        # stop streaming before anything else
        self.odrive.running = False
        if self._stream_thread:
            self._stream_thread.join(timeout=1.0)
            self._stream_thread = None

    def disarm(self):
        # 1) stop the stream
        self.stop()
        # 2) send IDLE & close CAN
        self.odrive.shutdown()

    async def calibrate(self, state: int = 3, save_config: bool = False) -> dict:
        """
        Delegate to the ODriveCalibrator for the CANSimple calibration flow.
        """
        return await self.calibrator.run(state=state, save_config=save_config)

    async def configure(self, save_config: bool = False) -> dict:
        # if you’re already armed, disarm so the configurator can open a fresh bus
        if getattr(self, "_initialized", False):
            self.disarm()
            setattr(self, "_initialized", False)
        # now delegate to the configurator’s `restore(...)` method
        return await self.configurator.restore(save_config=save_config)