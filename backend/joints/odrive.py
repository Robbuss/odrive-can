import struct, time, threading
from backend.joints.base import Joint
from backend.odrive import ODriveCAN, CLOSED_LOOP, IDLE, _SET_INPUT_POS
from backend.calibration.odrive_calibrator import ODriveCalibrator

class ODriveJoint(Joint):
    def __init__(self, odrive: ODriveCAN):
        self.odrive = odrive
        self._stream_thread = None
        self.calibrator = ODriveCalibrator(can_bus=self.odrive, node_id=self.odrive.node)

    def initialize(self):
        """
        Open CAN bus and arm closed-loop.
        """
        self.odrive.initialize()

    def move(self, delta: float, freq: float = 100.0):
        start = self.odrive.read_turns()
        target = start + delta
        threading.Thread(
            target=lambda: self.odrive.stream_pos(target, freq), 
            daemon=True
        ).start()
        return {"start": start, "target": target, "freq": freq}

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