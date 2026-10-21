"""Build small, valid FIT files for tests: ``record`` messages and, optionally, ``lap`` ones.

Implements just enough of the FIT format: a 14-byte header, a definition
message for each kind of message (global 20, ``record``, and 19, ``lap``) and a
data message per sample or lap, with the FIT CRC-16 on the header and the
whole file.
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
_CADENCE = (4, 1, 0x02)  # cadence(uint8), one foot's steps a minute
# timestamp, start_time, total_elapsed_time and total_timer_time (uint32 ms),
# intensity(enum), lap_trigger(enum), wkt_step_index(uint16)
_LAP_FIELDS = (
    (253, 4, 0x86),
    (2, 4, 0x86),
    (7, 4, 0x86),
    (8, 4, 0x86),
    (23, 1, 0x00),
    (24, 1, 0x00),
    (71, 2, 0x84),
)


def _crc(data, crc=0):
    for byte in data:
        for nibble in (byte & 0xF, byte >> 4):
            tmp = _CRC_TABLE[crc & 0xF]
            crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ _CRC_TABLE[nibble]
    return crc


def _definition(local, number, fields):
    message = struct.pack("<BBBHB", 0x40 | local, 0, 0, number, len(fields))
    for field_number, size, base_type in fields:
        message += struct.pack("<BBB", field_number, size, base_type)
    return message


def _fit_time(when):
    return int((when.replace(tzinfo=UTC) - FIT_EPOCH).total_seconds())


def build_fit(samples, laps=()):
    """Return FIT bytes for ``samples`` and the watch's ``laps``.

    ``samples`` are ``(datetime_utc, heart_rate, metres, metres_per_second)``
    tuples, with a fifth item for cadence (one foot's steps a minute, as FIT
    stores it) when the watch measured one. ``laps`` are
    ``(start_utc, seconds, intensity, trigger, step)`` in FIT's numbers
    (intensity 0 active, 1 rest, 2 warm-up, 3 cool-down, 4 recovery; trigger
    0 manual, 1 time, 2 distance, 7 session end) and ``step`` may be ``None``.
    ``None`` heart rates, speeds and cadences are written as FIT "invalid" values.
    """
    with_cadence = any(len(sample) > 4 for sample in samples)
    records = bytearray(_definition(0, 20, _FIELDS + ((_CADENCE,) if with_cadence else ())))
    for when, heart_rate, metres, speed, *cadence in samples:
        records += struct.pack(
            "<BIBIH",
            0x00,
            _fit_time(when),
            0xFF if heart_rate is None else heart_rate,
            round(metres * 100),
            0xFFFF if speed is None else round(speed * 1000),
        )
        if with_cadence:
            value = cadence[0] if cadence else None
            records += struct.pack("<B", 0xFF if value is None else value)
    if laps:
        records += _definition(1, 19, _LAP_FIELDS)
        for start, seconds, intensity, trigger, step in laps:
            records += struct.pack(
                "<BIIIIBBH",
                0x01,
                _fit_time(start) + round(seconds),
                _fit_time(start),
                round(seconds * 1000),
                round(seconds * 1000),
                intensity,
                trigger,
                0xFFFF if step is None else step,
            )
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(records), b".FIT")
    header += struct.pack("<H", _crc(header))
    body = header + records
    return body + struct.pack("<H", _crc(body))


# struct codes and "invalid" values of the FIT base types FitWriter writes
_CODES = {0x00: "B", 0x01: "b", 0x02: "B", 0x83: "h", 0x84: "H", 0x85: "i", 0x86: "I", 0x07: "s"}
_CODES.update({0x0A: "B", 0x8B: "H", 0x8C: "I", 0x0D: "B"})
_INVALID = {0x00: 0xFF, 0x01: 0x7F, 0x02: 0xFF, 0x83: 0x7FFF, 0x84: 0xFFFF, 0x85: 0x7FFFFFFF}
_INVALID.update({0x86: 0xFFFFFFFF, 0x0A: 0, 0x8B: 0, 0x8C: 0, 0x0D: 0xFF})


class FitWriter:
    """Writes FIT messages field by field, for files a watch could write but build_fit can't.

    Definitions can be big-endian or carry developer fields, data messages can
    use compressed timestamp headers, and :meth:`chain` starts another FIT file
    in the same bytes.
    """

    def __init__(self):
        self.files, self.body, self.definitions = [], bytearray(), {}

    def define(self, local, number, fields, big_endian=False, developer=()):
        """Define ``local`` as message ``number`` with ``(field, size, base type)`` fields.

        ``developer`` fields are ``(number, size, developer data index)``.
        """
        endian = ">" if big_endian else "<"
        self.body += struct.pack("<BBB", 0x40 | local | (0x20 if developer else 0), 0, big_endian)
        self.body += struct.pack(endian + "HB", number, len(fields))
        self.body += b"".join(bytes(field) for field in fields)
        if developer:
            self.body += bytes([len(developer)]) + b"".join(bytes(field) for field in developer)
        self.definitions[local] = (endian, fields, developer)

    def data(self, local, *values, time_offset=None):
        """A data message: a raw value per field (``None`` writes it invalid, a tuple an array)."""
        endian, fields, developer = self.definitions[local]
        compressed = 0x80 | (local << 5) | time_offset if time_offset is not None else local
        self.body.append(compressed)
        for (_number, size, base), value in zip(fields, values, strict=True):
            code = _CODES[base]
            if code == "s":
                self.body += (value or b"").ljust(size, b"\0")
                continue
            count = size // struct.calcsize(code)
            value = _INVALID[base] if value is None else value
            items = value if isinstance(value, tuple) else (value,) * count
            self.body += struct.pack(endian + code * count, *items)
        self.body += bytes(sum(size for _number, size, _index in developer))

    def chain(self):
        """Finish this FIT file; what follows goes in the next one."""
        self.files.append(bytes(self.body))
        self.body, self.definitions = bytearray(), {}

    def bytes(self):
        """The FIT files written, one after another, with headers and CRCs."""
        out = b""
        for records in [*self.files, bytes(self.body)]:
            header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(records), b".FIT")
            header += struct.pack("<H", _crc(header))
            body = header + records
            out += body + struct.pack("<H", _crc(body))
        return out


def fit_time(when):
    """A naive UTC datetime as a FIT timestamp."""
    return _fit_time(when)
