import struct, time
from backend.joints.base import Joint
from backend.odrive.can_simple import ODriveCAN, CLOSED_LOOP, IDLE

class ODriveJoint(Joint):
    def __init__(self, odrive: ODriveCAN):
        self.odrive = odrive

    def initialize(self):
        self.odrive.initialize()

    def move(self, delta: float, freq: float = 100.0):
        current = self.odrive.read_turns()
        target = current + delta
        self.odrive.stream_pos(target, freq)
        return {"start": current, "target": target, "freq": freq}

    def stop(self):
        self.odrive.stop()

    def status(self) -> dict:
        return self.odrive.status()