import logging
import moteus
from backend.can_bus import CANBus

logger = logging.getLogger(__name__)

class MoteusBus:
    def __init__(self,
                 device: str = "/dev/ttyACM0",
                 node_id: int = 0,
                 fd: bool = True,
                 use_fdcanusb: bool = True):
        self.device = device
        self.node_id = node_id
        self.fd = fd
        self.use_fdcanusb = use_fdcanusb
        self._ctrl = None


    def open(self):
        if self._ctrl is not None:
            return

        # build and explicitly open the Fdcanusb transport so it really
        # binds to the USB-CDC device and negotiates CAN-FD
        transport = moteus.Fdcanusb(path=self.device)
        logger.info(
            "Opening Moteus Controller on %s via Fdcanusb(fd=%s)",
            self.device, self.fd,
        )
        self._ctrl = moteus.Controller(
            id=self.node_id,
            transport=transport,
        )

    async def send_command(self, **kwargs):
        self.open()
        try:
            # ask for a reply by setting query=True
            return await self._ctrl.cycle(query=True, **kwargs)
        except Exception as e:
            logger.error("Error sending command: %s", e)
            raise

    async def query(self):
        self.open()
        try:
            return await self._ctrl.query()
        except Exception as e:
            logger.error("Error querying controller: %s", e)
            raise

    def shutdown(self) -> None:
        """
        Tear down the controller reference and any CANBus if used.
        """
        if self._ctrl is not None:
            logger.info("Shutting down Moteus Controller on %s", self.device)
            self._ctrl = None
        if self._canbus is not None:
            self._canbus.shutdown()
            self._canbus = None
