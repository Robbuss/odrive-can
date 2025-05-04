import struct, time, threading
from backend.joints.base import Joint
from backend.joints.odrive.transport import ODriveCAN, CLOSED_LOOP, IDLE, _SET_INPUT_POS, _SET_TRAJ_VEL_LIMIT, INPUT_MODE_TRAP_TRJ, INPUT_MODE_POS_FILTER
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

    def move(self,
             delta: float,
             max_vel: float = None  # turns/sec
    ) -> dict:
        """
        Send a single position setpoint, optionally first setting
        a maximum trajectory velocity (turns/sec).
        """
        # 1) Arm if needed
        if not getattr(self, "_initialized", False):
            self.initialize()
            setattr(self, "_initialized", True)

        # 2) Read current & compute target
        start  = self.odrive.read_turns()
        target = start + delta

        # 3) If caller requested a speed limit, send that first
        if max_vel is not None:
            self.odrive.set_input_mode(INPUT_MODE_TRAP_TRJ)
            self.odrive.set_traj_vel_limit(float(max_vel))
        else:
            self.odrive.set_input_mode(INPUT_MODE_POS_FILTER)            

        # 4) Finally send the new position
        arb_pos  = (self.odrive.node << 5) | _SET_INPUT_POS
        data_pos = struct.pack('<fhh', target, 0, 0)
        self.odrive.send(arb_pos, data_pos)

        return {"start": start, "target": target, "max_vel": max_vel}

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