"""AOSP VehicleProperty enums for constructing property IDs."""

from enum import IntEnum


class VehiclePropertyGroup(IntEnum):
    SYSTEM = 0x10000000
    VENDOR = 0x20000000


class VehicleArea(IntEnum):
    GLOBAL = 0x01000000
    WINDOW = 0x03000000
    MIRROR = 0x04000000
    SEAT = 0x05000000
    DOOR = 0x06000000
    WHEEL = 0x07000000


class VehiclePropertyType(IntEnum):
    STRING = 0x00100000
    BOOLEAN = 0x00200000
    INT32 = 0x00400000
    INT32_VEC = 0x00410000
    INT64 = 0x00500000
    INT64_VEC = 0x00510000
    FLOAT = 0x00600000
    FLOAT_VEC = 0x00610000
    BYTES = 0x00700000
    MIXED = 0x00E00000


class VehiclePropertyAccess(IntEnum):
    NONE = 0x00
    READ = 0x01
    WRITE = 0x02
    READ_WRITE = 0x03


class VehiclePropertyChangeMode(IntEnum):
    STATIC = 0x00
    ON_CHANGE = 0x01
    CONTINUOUS = 0x02


class VehicleAreaDoor(IntEnum):
    ROW_1_LEFT = 0x00000001
    ROW_1_RIGHT = 0x00000004
    ROW_2_LEFT = 0x00000010
    ROW_2_RIGHT = 0x00000040
