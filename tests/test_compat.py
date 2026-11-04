"""Tests for the jellyfishlights-py workarounds."""

import json
import threading

from jellyfishlightspy import PatternConfig, RunConfig
from jellyfishlightspy.helpers import from_json, to_json
from jellyfishlightspy.requests import (
    GetPatternConfigRequest,
    GetZoneStateRequest,
    SetZoneStateRequest,
)

from .conftest import pattern_list_message, push, run_pattern_message

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


ZONES = json.dumps(
    {
        "cmd": "fromCtlr",
        "zones": {
            "Front": {
                "numPixels": 10,
                "portMap": [
                    {
                        "phyPort": 1,
                        "phyStartIdx": 0,
                        "phyEndIdx": 9,
                        "zoneRGBStartIdx": 0,
                    }
                ],
            }
        },
    }
)


def answer(client, request_type, message):
    """Makes the mocked controller answer a request type with a raw message.

    The answer arrives shortly after the request, like a real reply, because
    the library only accepts data received after it starts waiting.
    """
    monitor = client._controller._JellyFishController__ws_monitor

    def send(request):
        if isinstance(request, request_type):
            threading.Timer(0.05, monitor.on_message, (None, message)).start()

    client._controller._JellyFishController__send.side_effect = send


async def test_refresh_after_running_music_pattern(hass, client):
    # The refresh light.turn_on does after applying an effect (issue #44)
    await push(hass, client, ZONES)
    answer(client, GetZoneStateRequest, run_pattern_message(MUSIC_PATTERN, MUSIC))

    await client.async_get_zone_states("Front")

    assert client.states["Front"].is_on
    assert client.states["Front"].file == MUSIC_PATTERN
    assert client.states["Front"].brightness == 100


async def test_apply_music_pattern_with_brightness(hass, client):
    await push(hass, client, pattern_list_message(MUSIC_PATTERN))
    folder, name = MUSIC_PATTERN.split("/")
    answer(
        client,
        GetPatternConfigRequest,
        json.dumps(
            {
                "cmd": "fromCtlr",
                "patternFileData": {
                    "folders": folder,
                    "name": name,
                    "jsonData": json.dumps(MUSIC),
                },
            }
        ),
    )

    await client.async_apply_pattern(MUSIC_PATTERN, "Front", 40)

    request = client._controller._JellyFishController__send.call_args.args[0]
    assert isinstance(request, SetZoneStateRequest)
    sent = json.loads(json.loads(to_json(request))["runPattern"]["data"])
    assert sent["musicSettings"] == MUSIC["musicSettings"]
    assert sent["runData"]["brightness"] == 40
