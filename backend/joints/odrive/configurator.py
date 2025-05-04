import asyncio
import struct
import math
import json
from pathlib import Path

from backend.can_bus import CANBus
from backend.joints.odrive.node import CanSimpleNode, REBOOT_ACTION_SAVE

# SDO opcodes and formats
_OPCODE_READ  = 0x00
_OPCODE_WRITE = 0x01
_RX_SDO       = 0x04
_TX_SDO       = 0x05
_GET_VERSION  = 0x00

_FORMAT_LOOKUP = {
    'bool':   '?',
    'uint8':  'B', 'int8':  'b',
    'uint16': 'H', 'int16': 'h',
    'uint32': 'I', 'int32': 'i',
    'uint64': 'Q', 'int64': 'q',
    'float':  'f',
}


class ODriveConfigurator:
    """
    Reads flat_endpoints.json & config.json from the local `config/` folder,
    then applies them via CANSimple SDO.
    """

    def __init__(self, can_bus: CANBus, node_id: int):
        self.can_bus = can_bus
        self.node_id = node_id

        # locate our config dir, relative to this file
        cfg_dir = Path(__file__).parent / "config"
        if not cfg_dir.is_dir():
            raise FileNotFoundError(f"Config folder not found: {cfg_dir}")

        # load the endpoint schema
        endpoints_path = cfg_dir / "flat_endpoints.json"
        if not endpoints_path.is_file():
            raise FileNotFoundError(f"Missing {endpoints_path.name}")
        self.endpoint_data = json.loads(endpoints_path.read_text())

        # load the actual config to write
        config_path = cfg_dir / "config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"Missing {config_path.name}")
        self.config_data = json.loads(config_path.read_text())

    async def version_check(self):
        """
        Make sure the flat_endpoints.json matches the ODrive's HW/FW.
        """
        if not self.can_bus.bus:
            self.can_bus.open()

        # ask for version
        arb = (self.node_id << 5) | _GET_VERSION
        self.can_bus.send(arb, b'')
        msg = await CanSimpleNode(self.can_bus.bus, self.node_id).await_msg(_GET_VERSION)

        # unpack
        _, pl, hw_v, hw_var, fw_maj, fw_min, fw_rev, _ = struct.unpack('<BBBBBBBB', msg.data)
        hw_str = f"{pl}.{hw_v}.{hw_var}"
        fw_str = f"{fw_maj}.{fw_min}.{fw_rev}"

        if self.endpoint_data['hw_version'] != hw_str:
            raise RuntimeError(f"HW mismatch: {self.endpoint_data['hw_version']} != {hw_str}")
        if self.endpoint_data['fw_version'] != fw_str:
            raise RuntimeError(f"FW mismatch: {self.endpoint_data['fw_version']} != {fw_str}")

    async def write_and_verify(self, node: CanSimpleNode, path: str, val):
        """
        Write one endpoint and immediately read it back to verify.
        """
        info = self.endpoint_data['endpoints'][path]
        eid  = info['id']
        typ  = info['type']
        fmt  = _FORMAT_LOOKUP[typ]

        arb = (self.node_id << 5) | _RX_SDO
        # pack the write SDO
        payload = struct.pack(f'<BHB{fmt}', _OPCODE_WRITE, eid, 0, val)
        self.can_bus.send(arb, payload)

        # allow the device to ack then flush
        await asyncio.sleep(0.01)
        node.flush_rx()

        # now read it back
        payload = struct.pack('<BHB', _OPCODE_READ, eid, 0)
        self.can_bus.send(arb, payload)

        msg = await node.await_msg(_TX_SDO)
        _, _, _, ret = struct.unpack_from(f'<BHB{fmt}', msg.data)

        # floats need 32-bit pruning
        if typ == 'float':
            val32 = struct.unpack('<f', struct.pack('<f', val))[0]
            if math.isnan(val32):
                ok = math.isnan(ret)
            else:
                ok = (ret == val32)
            if not ok:
                raise RuntimeError(f"Write failed for {path}: got {ret}, expected {val32}")
        else:
            if ret != val:
                raise RuntimeError(f"Write failed for {path}: got {ret}, expected {val}")

    async def restore(self, save_config: bool = False) -> dict:
        """
        Write **all** entries from config.json and optionally reboot.
        """
        # ensure CAN bus is open
        if not self.can_bus.bus:
            self.can_bus.open()

        written: dict[str, Any] = {}
        node = CanSimpleNode(self.can_bus.bus, self.node_id)
        with node:
            # sanity‐check the JSON schema
            await self.version_check()

            # drop any old frames
            await asyncio.sleep(0.1)
            node.flush_rx()

            # write them all and record each value
            for path, val in self.config_data.items():
                if path not in self.endpoint_data['endpoints']:
                    raise KeyError(f"Unknown endpoint path: {path}")
                await self.write_and_verify(node, path, val)
                written[path] = val

            # finally save & reboot if asked
            if save_config:
                node.reboot_msg(REBOOT_ACTION_SAVE)

        return {
            "status":  "restored",
            "written": written
        }