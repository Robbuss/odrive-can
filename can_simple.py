import can, struct, time, signal, sys, argparse

# CANSimple opcodes & states
_SET_AXIS_STATE = 0x07
_HEARTBEAT      = 0x01
_ENCODER_EST    = 0x09
_SET_INPUT_POS  = 0x0C
IDLE            = 1
CLOSED_LOOP     = 8

class ODriveCAN:
    def __init__(self, iface, node, cpr):
        self.iface   = iface
        self.node    = node
        self.cpr     = cpr
        self.bus     = None
        self.running = False

    def open(self):
        self.bus = can.interface.Bus(channel=self.iface,
                                     interface="socketcan")
        while self.bus.recv(timeout=0): pass

    def send_state(self, st):
        msg = can.Message(arbitration_id=(self.node<<5)|_SET_AXIS_STATE,
                          data=struct.pack('<I', st),
                          is_extended_id=False)
        self.bus.send(msg)

    def wait_heartbeat(self, want, timeout=5):
        stop = time.time()+timeout
        while time.time()<stop:
            m = self.bus.recv(timeout=0.1)
            if m and m.arbitration_id==(self.node<<5|_HEARTBEAT):
                _, st, *_ = struct.unpack('<IBBB', m.data[:7])
                if st==want:
                    return True
        return False

    def read_turns(self, timeout=2):
        stop = time.time()+timeout
        while time.time()<stop:
            m = self.bus.recv(timeout=0.1)
            if m and m.arbitration_id==(self.node<<5|_ENCODER_EST):
                turns, _ = struct.unpack('<ff', m.data)
                return turns
        raise RuntimeError("no encoder estimate")

    def stream_pos(self, target_turns, freq=100):
        period = 1/freq
        self.running = True
        try:
            while self.running:
                data = struct.pack('<fhh', target_turns, 0, 0)
                self.bus.send(can.Message(
                    arbitration_id=(self.node<<5)|_SET_INPUT_POS,
                    data=data, is_extended_id=False))
                time.sleep(period)
        finally:
            self.disarm()

    def disarm(self):
        print("\nDisarming…")
        self.send_state(IDLE)
        if self.wait_heartbeat(IDLE, timeout=2):
            print(" → Axis is IDLE")
        else:
            print(" ⚠️ No IDLE confirmation")
        if self.bus:
            self.bus.shutdown()
        self.running = False

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-i","--iface", default="can0")
    p.add_argument("-n","--node",  type=int, default=0)
    p.add_argument("-c","--cpr",   type=int, default=4096)
    p.add_argument("-d","--delta", type=float, default=2.5)
    p.add_argument("-f","--freq",  type=float, default=100)
    args = p.parse_args()

    od = ODriveCAN(args.iface, args.node, args.cpr)
    od.open()

    print("→ Arming CLOSED_LOOP_CONTROL")
    od.send_state(CLOSED_LOOP)
    if not od.wait_heartbeat(CLOSED_LOOP):
        print("❌ Failed to enter closed-loop")
        sys.exit(1)

    start = od.read_turns()
    target = start + args.delta
    print(f"Current: {start:.3f} turns → Target: {target:.3f} turns")

    # catch Ctrl-C
    signal.signal(signal.SIGINT,  lambda *a: setattr(od, 'running', False))
    signal.signal(signal.SIGTERM, lambda *a: setattr(od, 'running', False))

    od.stream_pos(target, freq=args.freq)

if __name__=="__main__":
    main()