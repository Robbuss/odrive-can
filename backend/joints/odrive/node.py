import time
import asyncio
import can
import struct

# CANSimple command IDs
ADDRESS_CMD = 0x06
SET_AXIS_STATE_CMD = 0x07
REBOOT_CMD = 0x16
CLEAR_ERRORS_CMD = 0x18

# Reboot actions
REBOOT_ACTION_REBOOT = 0
REBOOT_ACTION_SAVE = 1
REBOOT_ACTION_ERASE = 2

class CanSimpleNode:
    """
    Minimal CANSimple helper, using blocking recv to avoid notifier threads.
    """
    def __init__(self, bus: can.Bus, node_id: int):
        self.bus = bus
        self.node_id = node_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def flush_rx(self):
        # Drain any available messages
        while True:
            msg = self.bus.recv(timeout=0)
            if not msg:
                break

    async def await_msg(self, cmd_id: int, timeout: float = 1.0):
        """
        Await the next message with the specified cmd_id by polling bus.recv.
        """
        arb_id = (self.node_id << 5) | cmd_id
        loop = asyncio.get_running_loop()

        def _recv_blocking():
            end = time.time() + timeout
            while time.time() < end:
                msg = self.bus.recv(timeout=0.1)
                if msg and msg.arbitration_id == arb_id:
                    return msg
            raise TimeoutError(f"No message for cmd_id {cmd_id}")

        return await loop.run_in_executor(None, _recv_blocking)

    def clear_errors_msg(self, identify: bool = False):
        """
        Send the CLEAR_ERRORS_CMD.
        If `identify` is True, send 0x01, else send 0x00.
        """
        data = b'\x01' if identify else b'\x00'
        arb = (self.node_id << 5) | CLEAR_ERRORS_CMD
        self.bus.send(can.Message(
            arbitration_id=arb,
            data=data,
            is_extended_id=False
        ))

    def reboot_msg(self, action: int):
        arb = (self.node_id << 5) | REBOOT_CMD
        self.bus.send(can.Message(arbitration_id=arb, data=[action], is_extended_id=False))

    def set_state_msg(self, state: int):
        arb = (self.node_id << 5) | SET_AXIS_STATE_CMD
        data = struct.pack('<I', state)
        self.bus.send(can.Message(arbitration_id=arb, data=data, is_extended_id=False))