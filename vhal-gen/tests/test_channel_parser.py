"""Tests for the channel parser."""

from pathlib import Path

from vhal_gen.models.signal import Direction
from vhal_gen.parser.channel_parser import build_pdu_direction_map, parse_channels

CHANNELS_FILE = (
    Path(__file__).parent.parent.parent
    / "flync-model-dev-2" / "flync-model-dev" / "general" / "channels" / "channels.yaml"
)


def test_parse_channels():
    """Verify channels.yaml is parsed correctly."""
    channels = parse_channels(CHANNELS_FILE)
    assert len(channels) == 18
    # First channel
    assert channels[0].name == "FD_CAN_ZC_FL_0"
    assert channels[0].protocol_type == "can_fd"


def test_pdu_direction_map():
    """Verify PDU direction mapping resolves correctly."""
    channels = parse_channels(CHANNELS_FILE)
    direction_map = build_pdu_direction_map(channels)

    # ExteriorLighting_Doors_Req (0x401) sent by zc_fl_controller to hpc → RX
    assert direction_map.get(0x401) == Direction.RX

    # ExteriorLighting_Doors_Cmd (0x101) sent by hpc to zc_fr → TX from IVI
    assert direction_map.get(0x101) == Direction.TX
