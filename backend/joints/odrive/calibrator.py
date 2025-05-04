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
        # 1) Ensure CAN bus is open
        if not self.can_bus.bus:
            self.can_bus.open()

        # 2) Perform calibration in a blocking‐recv helper
        with CanSimpleNode(bus=self.can_bus.bus, node_id=self.node_id) as node:
            node.clear_errors_msg()
            node.set_state_msg(state)

            # flush any chatter
            await asyncio.sleep(1.0)
            node.flush_rx()

            # 3) Wait for IDLE heartbeat, up to max_wait seconds
            max_wait = 30.0
            deadline = asyncio.get_event_loop().time() + max_wait

            error  = None
            result = None

            while True:
                now = asyncio.get_event_loop().time()
                remaining = deadline - now
                if remaining <= 0:
                    raise RuntimeError(f"Calibration timed out after {max_wait}s")

                # await the next HEARTBEAT (cmd_id=1)
                msg = await node.await_msg(0x01, timeout=remaining)
                error, st, result, _ = struct.unpack('<IBBB', bytes(msg.data[:7]))

                if st == IDLE:
                    break

            # 4) Check for failure codes
            if error != 0 or result != 0:
                raise RuntimeError(f"Calibration failed: error={error}, result={result}")

            # 5) Optionally save & reboot
            if save_config:
                node.reboot_msg(REBOOT_ACTION_SAVE)

        # 6) Return outcome
        return {
            "status": "calibrated",
            "error":  error,
            "result": result
        }