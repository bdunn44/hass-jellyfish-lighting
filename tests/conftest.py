"""Fixtures for JellyFish Lighting tests."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jellyfish_lighting.api import JellyfishLightingApiClient
from custom_components.jellyfish_lighting.const import (
    CONF_ADDRESS,
    CONF_HOSTNAME,
    CONF_NAME,
    CONF_VERSION,
    DOMAIN,
)

ADDRESS = "192.0.2.10"
HOSTNAME = "JellyFish-TEST.local"

# A library pattern as the app sends it, including a settings block the
# jellyfishlights-py models don't know about
FIREWORKS = {
    "colors": [254, 167, 3, 255, 72, 3, 255, 255, 255],
    "type": "Firework",
    "skip": 2,
    "numOfLeds": 6,
    "runData": {
        "speed": 1,
        "brightness": 100,
        "effect": "No Effect",
        "effectValue": 0,
        "rgbAdj": [100, 100, 100],
    },
    "direction": "Center",
    "fireworkSettings": {"spawnRate": 100, "colorPerLED": 3, "fireworkSpeed": 50},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the integration from custom_components."""
    yield


@pytest.fixture
def config_entry(hass):
    """A config entry whose stored version predates a firmware update."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Test JellyFish",
            CONF_HOSTNAME: HOSTNAME,
            CONF_VERSION: "3.1.4",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def client(hass, config_entry):
    """An API client that never touches the network."""
    api = JellyfishLightingApiClient(ADDRESS, config_entry, hass)
    api.async_connect = AsyncMock()
    api._controller._JellyFishController__send = Mock()
    return api


def run_pattern_message(file, data, state=1, zone="Front"):
    """A runPattern push as the controller sends it."""
    return json.dumps(
        {
            "cmd": "fromCtlr",
            "runPattern": {
                "activatedBy": "network_command",
                "data": json.dumps(data) if isinstance(data, dict) else data,
                "file": file,
                "id": zone,
                "state": state,
                "zoneName": [zone],
            },
        }
    )


def pattern_list_message(*patterns):
    """A patternFileList push listing patterns saved on the controller."""
    entries = []
    for pattern in patterns:
        folder, name = pattern.split("/")
        entries.append({"folders": folder, "name": "", "readOnly": True})
        entries.append({"folders": folder, "name": name, "readOnly": False})
    return json.dumps({"cmd": "fromCtlr", "patternFileList": entries})


async def push(hass, api, message):
    """Delivers a raw message through the library's WebSocket handler.

    Runs in an executor thread like the real WebSocket thread, so the library
    parses it and the integration's raw-message hook sees it.
    """
    monitor = api._controller._JellyFishController__ws_monitor
    await hass.async_add_executor_job(monitor.on_message, None, message)
    # The client hands work to the event loop with run_coroutine_threadsafe,
    # which async_block_till_done doesn't track
    for _ in range(5):
        await asyncio.sleep(0)
    await hass.async_block_till_done()
