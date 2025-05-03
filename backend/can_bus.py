import can

class CANBus:
    """
    Generic CAN bus manager. Handles open, send, receive, and shutdown.
    """
    def __init__(self, iface: str = "can0", channel_type: str = "socketcan"):
        self.iface = iface
        self.channel_type = channel_type
        self.bus = None

    def open(self):
        self.bus = can.interface.Bus(channel=self.iface,
                                     interface=self.channel_type)
        while self.bus.recv(timeout=0):
            pass

    def send(self, arbitration_id: int, data: bytes, extended_id: bool = False):
        msg = can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=extended_id
        )
        self.bus.send(msg)

    def recv(self, timeout: float = 1.0):
        return self.bus.recv(timeout=timeout)

    def shutdown(self):
        if self.bus:
            self.bus.shutdown()