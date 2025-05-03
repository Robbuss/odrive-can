import struct, time
from backend.can_bus import CANBus

# CANSimple opcodes & states
_SET_AXIS_STATE = 0x07
_HEARTBEAT      = 0x01
_ENCODER_EST    = 0x09
_SET_INPUT_POS  = 0x0C
IDLE            = 1
CLOSED_LOOP     = 8

class ODriveCAN(CANBus):
    def __init__(self, iface: str = "can0", node: int = 0, cpr: int = 4096):
        super().__init__(iface)
        self.node = node
        self.cpr = cpr
        self.running = False

    def initialize(self):
        self.open()
        self.send_state(CLOSED_LOOP)
        if not self._wait_state(CLOSED_LOOP):
            raise RuntimeError("Failed to enter CLOSED_LOOP")

    def send_state(self, state: int):
        arb = (self.node << 5) | _SET_AXIS_STATE
        data = struct.pack('<I', state)
        self.send(arb, data)

    def _wait_state(self, want: int, timeout: float = 5.0) -> bool:
        stop = time.time() + timeout
        while time.time() < stop:
            msg = self.recv(timeout=0.1)
            if msg and msg.arbitration_id == ((self.node << 5) | _HEARTBEAT):
                _, state, *_ = struct.unpack('<IBBB', msg.data[:7])
                if state == want:
                    return True
        return False

    def read_turns(self, timeout: float = 2.0) -> float:
        stop = time.time() + timeout
        arb = (self.node << 5) | _ENCODER_EST
        while time.time() < stop:
            msg = self.recv(timeout=0.1)
            if msg and msg.arbitration_id == arb:
                turns, _ = struct.unpack('<ff', msg.data)
                return turns
        raise RuntimeError("No encoder estimate")

    def stream_pos(self, target_turns: float, freq: float = 100.0):
        period = 1.0 / freq
        self.running = True
        def _stream():
            try:
                while self.running:
                    payload = struct.pack('<fhh', target_turns, 0, 0)
                    arb = (self.node << 5) | _SET_INPUT_POS
                    self.send(arb, payload)
                    time.sleep(period)
            finally:
                self.stop()
        import threading
        threading.Thread(target=_stream, daemon=True).start()

    def stop(self):
        self.running = False

    def status(self) -> dict:
        try:
            pos = self.read_turns(timeout=0.5)
        except RuntimeError:
            pos = None
        return {"position": pos, "running": self.running}

    def shutdown(self):
        self.send_state(IDLE)
        self.shutdown()