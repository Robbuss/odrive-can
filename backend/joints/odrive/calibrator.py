import asyncio
import struct

from backend.can_bus import CANBus
from backend.joints.odrive.transport import IDLE
from backend.joints.odrive.node import CanSimpleNode, REBOOT_ACTION_SAVE

class ODriveCalibrator:
    """
    Encapsulates the CANSimple calibration sequence for an ODrive node.
    """
    def __init__(self, can_bus: CANBus, node_id: int):
        self.can_bus = can_bus
        self.node_id = node_id

    async def run(self, state: int = 3, save_config: bool = False) -> dict:
        # Ensure CAN bus is open
        if not self.can_bus.bus:
            self.can_bus.open()

        # Use blocking recv-based helper
        with CanSimpleNode(bus=self.can_bus.bus, node_id=self.node_id) as node:
            node.clear_errors_msg()
            node.set_state_msg(state)

            # Flush any initial chatter
            await asyncio.sleep(1.0)
            node.flush_rx()

            # Wait for IDLE state
            error = None
            result = None
            while True:
                msg = await node.await_msg(0x01)
                error, st, result, _ = struct.unpack('<IBBB', bytes(msg.data[:7]))
                if st == IDLE:
                    break

            if error != 0 or result != 0:
                raise RuntimeError(f"Calibration failed: error={error}, result={result}")

            if save_config:
                node.reboot_msg(REBOOT_ACTION_SAVE)

        return {"status": "calibrated", "error": error, "result": result}