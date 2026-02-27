"""Data models for FLYNC signals, PDUs, and the overall model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    RX = "RX"
    TX = "TX"
    UNKNOWN = "UNKNOWN"


@dataclass
class ValueTableEntry:
    num_value: int
    description: str


@dataclass
class Signal:
    name: str
    description: str
    bit_length: int
    base_data_type: str  # bool, uint8, uint16, uint32
    endianness: str  # little, big
    lower_limit: float = 0
    upper_limit: float = 0
    scale: float = 1.0
    offset: float = 0.0
    compu_methods: list[str] = field(default_factory=list)
    value_table: list[ValueTableEntry] = field(default_factory=list)
    # Computed at parse time
    start_bit: int = 0
    bitmask: int = 0

    def __post_init__(self):
        if self.bitmask == 0:
            self.bitmask = (1 << self.bit_length) - 1


@dataclass
class PDU:
    name: str
    pdu_id: int
    length: int  # bytes
    pdu_type: str
    signals: list[Signal] = field(default_factory=list)
    direction: Direction = Direction.UNKNOWN


@dataclass
class GlobalState:
    name: str
    state_id: int
    participants: list[str] = field(default_factory=list)
    is_default: bool = False


@dataclass
class ChannelMessage:
    name: str
    frame_id: int
    protocol: str
    sender: str
    receivers: list[str] = field(default_factory=list)
    pdu_id: Optional[int] = None


@dataclass
class Channel:
    name: str
    protocol_type: str
    bus_hw_id: int
    messages: list[ChannelMessage] = field(default_factory=list)


@dataclass
class FlyncModel:
    pdus: dict[str, PDU] = field(default_factory=dict)  # keyed by PDU name
    channels: list[Channel] = field(default_factory=list)
    global_states: list[GlobalState] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
