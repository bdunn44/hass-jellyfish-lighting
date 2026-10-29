"""Tests for capturing patterns the JellyFish app runs from its library."""

import copy
from datetime import timedelta
import json

import pytest

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.jellyfish_lighting.api import JellyfishLightingApiClient
from jellyfishlightspy.helpers import to_json

from .conftest import (
    ADDRESS,
    FIREWORKS,
    pattern_list_message,
    push,
    run_pattern_message,
)

PATTERN = "Halloween/Candy Corn Fireworks"


def stored(api):
    return {name: json.loads(data) for name, data in api._captured.items()}


async def test_captures_playing_pattern_with_unknown_settings(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))

    assert stored(client) == {PATTERN: FIREWORKS}
    assert PATTERN in client.patterns


@pytest.mark.parametrize(
    ("file", "state"),
    [
        (PATTERN, 0),  # Zone off: reported on every connect, not an app run
        ("", 1),
        ("No Folder", 1),
        ("_JF-CUSTOM/Custom Chase", 1),  # Unsaved look, as firmware 4.6.1 names it
    ],
)
async def test_ignores(hass, client, file, state):
    await push(hass, client, run_pattern_message(file, FIREWORKS, state=state))

    assert client._captured == {}


async def test_ignores_invalid_data(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, "not json"))

    assert client._captured == {}


async def test_ignores_pattern_saved_on_controller(hass, client):
    await push(hass, client, pattern_list_message(PATTERN))
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))

    assert client._captured == {}
    assert client.patterns == [PATTERN]


async def test_prunes_saved_pattern_captured_before_list(hass, client):
    # On connect the controller pushes zone states before its pattern list
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))
    await push(hass, client, pattern_list_message(PATTERN))

    assert client._captured == {}
    assert client.patterns == [PATTERN]


async def test_latest_capture_wins_but_keeps_brightness(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))

    updated = copy.deepcopy(FIREWORKS)
    updated["colors"] = [255, 0, 0]
    updated["runData"]["speed"] = 5
    updated["runData"]["brightness"] = 40
    await push(hass, client, run_pattern_message(PATTERN, updated))

    expected = copy.deepcopy(updated)
    expected["runData"]["brightness"] = 100
    assert stored(client) == {PATTERN: expected}


async def test_replay_and_echo_leave_definition_unchanged(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))
    send = client._controller._JellyFishController__send

    await client.async_apply_pattern(PATTERN, "Front", brightness=50)

    request = json.loads(to_json(send.call_args.args[0]))["runPattern"]
    sent = json.loads(request["data"])
    assert request["file"] == PATTERN
    assert request["zoneName"] == ["Front"]
    assert sent["runData"]["brightness"] == 50
    assert sent["fireworkSettings"] == FIREWORKS["fireworkSettings"]

    # The controller echoes the replay back to every client
    await push(hass, client, run_pattern_message(PATTERN, sent))
    assert stored(client) == {PATTERN: FIREWORKS}


async def test_forget(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))

    assert client.async_forget_captured_pattern(PATTERN)
    assert client._captured == {}
    assert PATTERN not in client.patterns
    assert not client.async_forget_captured_pattern(PATTERN)


async def test_forgotten_pattern_stays_forgotten_when_zone_is_off(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))
    client.async_forget_captured_pattern(PATTERN)

    # Reconnecting reports the zone's last pattern with the zone off
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS, state=0))

    assert client._captured == {}


async def test_persists_across_clients(hass, hass_storage, client, config_entry):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()

    reloaded = JellyfishLightingApiClient(ADDRESS, config_entry, hass)
    await reloaded.async_load_captured_patterns()

    assert stored(reloaded) == {PATTERN: FIREWORKS}
    assert reloaded.patterns == [PATTERN]
