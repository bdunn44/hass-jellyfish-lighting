"""Tests for the jellyfishlights-py workarounds."""

import json

from jellyfishlightspy import PatternConfig, RunConfig
from jellyfishlightspy.helpers import from_json, to_json

from .conftest import push, run_pattern_message

MUSIC_PATTERN = "_JF-MUSIC/Music Halloween bar or"

# A Music Box pattern as the controller reports it (from issue #44)
MUSIC = {
    "type": "Music",
    "colors": [80, 0, 120, 255, 60, 0, 0, 180, 0, 255, 140, 0, 148, 0, 211],
    "spaceBetweenPixels": 1,
    "effectBetweenPixels": "No Color Transform",
    "skip": 1,
    "numOfLeds": 1,
    "runData": {
        "speed": 1,
        "brightness": 100,
        "effect": "No Effect",
        "effectValue": 0,
        "rgbAdj": [100, 100, 100],
    },
    "direction": "Left",
    "musicSettings": {
        "musicType": "Bar Overlay",
        "frequencies": ["Bass"],
        "frequencyMultipliers": [1.0],
        "colors": [
            {"R": 255, "G": 40, "B": 0},
            {"R": 0, "G": 0, "B": 0},
            {"R": 50, "G": 0, "B": 50},
        ],
        "beatThreshold": 50.0,
        "direction": "center",
        "tipSize": 2,
    },
}


async def test_music_pattern_updates_zone_state(hass, client):
    await push(hass, client, run_pattern_message(MUSIC_PATTERN, MUSIC))

    state = client._controller.zone_states["Front"]
    assert state.file == MUSIC_PATTERN
    assert isinstance(state.data, PatternConfig)
    assert state.data.type == "Music"
    assert isinstance(state.data.runData, RunConfig)
    assert state.data.musicSettings == MUSIC["musicSettings"]


async def test_music_settings_survive_round_trip(client):
    config = from_json(json.dumps(MUSIC))
    config.runData.brightness = 40

    sent = json.loads(to_json(config))
    assert sent["musicSettings"] == MUSIC["musicSettings"]
    assert sent["runData"]["brightness"] == 40
