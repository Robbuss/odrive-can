import subprocess
import time
import os
import signal
import can

class CANBus:
    """
    Generic CAN bus manager. On can1+fd=True it will
    automatically launch the MJBots FDCAN-USB daemon
    and put the interface into FD mode.
    """
    def __init__(self,
                 iface: str = "can0",
                 bustype: str = "socketcan",
                 fd: bool = False,
                 node_id: int = 0):
        self.iface = iface
        self.bustype = bustype
        self.fd = fd
        self.node_id = node_id
        self.bus = None
        self._daemon = None

    def open(self):
        # If FD on can1, start the usb↔fd-can daemon
        if self.fd and self.iface == "can1":
            # wait for the serial-by-id symlink
            for _ in range(30):
                if os.path.exists("/dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("FDCAN-USB adapter never appeared")

            # launch the fdcanusb-daemon
            self._daemon = subprocess.Popen([
                "/usr/local/bin/fdcanusb-daemon",
                "-d", "/dev/serial/by-id/usb-mjbots_fdcanusb_E6F9844A-if00",
                "-i", "can1",
                "--bitrate",  "500000",
                "--fd-bitrate", "5000000",
            ])
            # give the daemon a moment to register can1
            time.sleep(0.1)

            # bring the interface up in FD mode
            subprocess.run([
                "ip", "link", "set", "can1", "up",
                "type", "can",
                "bitrate", "500000",
                "dbitrate", "5000000",
                "fd", "on",
            ], check=True)

        # Finally open python-can
        self.bus = can.interface.Bus(
            channel=self.iface,
            interface=self.bustype,
            fd=self.fd
        )
        # flush any old frames
        while self.bus.recv(timeout=0):
            pass

    def send(self, arbitration_id: int, data: bytes, extended_id: bool = False, is_fd: bool = None):
        msg = can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=extended_id,
            is_fd = self.fd if is_fd is None else is_fd
        )
        self.bus.send(msg)

    def recv(self, timeout: float = 1.0):
        return self.bus.recv(timeout=timeout)

    def shutdown(self):
        if self.bus:
            self.bus.shutdown()
            self.bus = None
        # tear down can1 and kill daemon if we started one
        if self.fd and self.iface == "can1":
            subprocess.run(["ip", "link", "set", "can1", "down"], check=True)
            if self._daemon:
                self._daemon.send_signal(signal.SIGTERM)
                self._daemon.wait()
                self._daemon = None