import asyncio
import struct
import math
import json
from pathlib import Path

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

    def __init__(self, node_id: int):
        self.node_id = node_id
