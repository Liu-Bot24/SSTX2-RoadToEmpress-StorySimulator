from __future__ import annotations

from typing import Any


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    start = offset
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 70:
            raise ValueError(f"varint too long at byte {start}")
    raise ValueError("truncated varint")


def parse_wire_fields(data: bytes) -> list[tuple[int, int, Any]]:
    offset = 0
    fields: list[tuple[int, int, Any]] = []
    while offset < len(data):
        key, offset = read_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 7

        if wire_type == 0:
            value, offset = read_varint(data, offset)
        elif wire_type == 1:
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            length, offset = read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
        elif wire_type == 5:
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"unsupported wire type {wire_type} at byte {offset}")

        fields.append((field_number, wire_type, value))
    return fields

