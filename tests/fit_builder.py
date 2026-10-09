"""Build small, valid FIT files for tests (``record`` messages only).

Implements just enough of the FIT format: a 14-byte header, one definition
message for global message 20 (``record``) and a data message per sample,
with the FIT CRC-16 on the header and the whole file.
"""

import struct
from datetime import UTC, datetime

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)
_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)  # fmt: skip

# field number, size, base type: timestamp(uint32), heart_rate(uint8), distance(uint32 cm), speed(uint16 mm/s)
_FIELDS = ((253, 4, 0x86), (3, 1, 0x02), (5, 4, 0x86), (6, 2, 0x84))


def _crc(data, crc=0):
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = _CRC_TABLE[crc & 0xF]
            crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ _CRC_TABLE[nibble]
    return crc


def build_fit(samples):
    """Return FIT bytes for ``samples``: ``(datetime_utc, heart_rate, metres, metres_per_second)`` tuples.

    ``None`` heart rates or speeds are written as FIT "invalid" values.
    """
    records = bytearray()
    records += struct.pack("<BBBHB", 0x40, 0, 0, 20, len(_FIELDS))
    for number, size, base_type in _FIELDS:
        records += struct.pack("<BBB", number, size, base_type)
    for when, heart_rate, metres, speed in samples:
        seconds = int((when.replace(tzinfo=UTC) - FIT_EPOCH).total_seconds())
        records += struct.pack(
            "<BIBIH",
            0x00,
            seconds,
            0xFF if heart_rate is None else heart_rate,
            round(metres * 100),
            0xFFFF if speed is None else round(speed * 1000),
        )
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(records), b".FIT")
    header += struct.pack("<H", _crc(header))
    body = header + records
    return body + struct.pack("<H", _crc(body))
