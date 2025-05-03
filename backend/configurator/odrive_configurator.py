import asyncio
import struct
import math

from backend.can_bus import CANBus
from backend.calibration.can_simple_node import CanSimpleNode, REBOOT_ACTION_SAVE

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
    Encapsulates reading/writing arbitrary endpoints
    via CANSimple SDO (flat_endpoints.json) protocol.
    """

    def __init__(self,
                 can_bus: CANBus,
                 node_id: int,
                 endpoint_data: dict):
        self.can_bus      = can_bus
        self.node_id      = node_id
        self.endpoint_data = endpoint_data

    async def version_check(self):
        """
        Verify the endpoints JSON matches the HW & FW version on the device.
        """
        # ensure bus open
        if not self.can_bus.bus:
            self.can_bus.open()

        # send read-version
        arb = (self.node_id << 5) | _GET_VERSION
        # empty payload
        self.can_bus.send(arb, b'')
        # await reply
        msg = await CanSimpleNode(self.can_bus.bus, self.node_id).await_msg(_GET_VERSION)

        # unpack
        _, product_line, hw_v, hw_variant, fw_maj, fw_min, fw_rev, _ = struct.unpack('<BBBBBBBB', msg.data)
        hw_str = f"{product_line}.{hw_v}.{hw_variant}"
        fw_str = f"{fw_maj}.{fw_min}.{fw_rev}"

        # compare
        if self.endpoint_data['hw_version'] != hw_str:
            raise RuntimeError(f"HW mismatch: {self.endpoint_data['hw_version']} != {hw_str}")
        if self.endpoint_data['fw_version'] != fw_str:
            raise RuntimeError(f"FW mismatch: {self.endpoint_data['fw_version']} != {fw_str}")

async def write_and_verify(self, node: CanSimpleNode, path: str, val):
    info = self.endpoint_data['endpoints'][path]
    eid  = info['id']
    typ  = info['type']
    fmt  = _FORMAT_LOOKUP[typ]

    arb = (self.node_id << 5) | _RX_SDO
    payload = struct.pack(f'<BHB{fmt}', _OPCODE_WRITE, eid, 0, val)
    self.can_bus.send(arb, payload)

    await asyncio.sleep(0.01)
    node.flush_rx()

    payload = struct.pack('<BHB', _OPCODE_READ, eid, 0)
    self.can_bus.send(arb, payload)

    msg = await node.await_msg(_TX_SDO)
    _, _, _, ret = struct.unpack_from(f'<BHB{fmt}', msg.data)

    # compare, pruning floats to 32‐bit first
    if typ == 'float':
        # prune to 32-bit float
        val_pruned = struct.unpack('<f', struct.pack('<f', val))[0]
        if math.isnan(val_pruned):
            ok = math.isnan(ret)
        else:
            ok = (ret == val_pruned)
        if not ok:
            raise RuntimeError(f"Write failed for {path}: {ret} != {val_pruned}")
    else:
        if ret != val:
            raise RuntimeError(f"Write failed for {path}: {ret} != {val}")

    async def restore(self,
                      config: dict,
                      save_config: bool = False) -> dict:
        """
        Write out all values in `config` (path->value) and optionally reboot.
        """
        # ensure bus open
        if not self.can_bus.bus:
            self.can_bus.open()

        # use blocking-polling CanSimpleNode
        node = CanSimpleNode(self.can_bus.bus, self.node_id)
        # no notifier threads, so just `with`
        with node:
            # check versions
            await self.version_check()

            # flush old messages
            await asyncio.sleep(0.1)
            node.flush_rx()

            # walk through config dict
            for path, val in config.items():
                if path not in self.endpoint_data['endpoints']:
                    raise KeyError(f"Unknown endpoint path: {path}")
                await self.write_and_verify(node, path, val)

            # final optional save
            if save_config:
                node.reboot_msg(REBOOT_ACTION_SAVE)

        return {
            "status":       "restored",
            "written_keys": list(config.keys())
        }