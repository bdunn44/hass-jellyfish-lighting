"""Tests for setting up the integration and its actions."""

from datetime import timedelta
import json
from unittest.mock import patch

import pytest

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.jellyfish_lighting import async_remove_config_entry_device
from custom_components.jellyfish_lighting.api import (
    JellyfishLightingApiClient,
    JellyFishLightingZoneData,
)
from custom_components.jellyfish_lighting.const import DOMAIN

from .conftest import FIREWORKS, HOSTNAME

PATTERN = "Halloween/Candy Corn Fireworks"


async def fake_get_data(self):
    """Populates the client as a poll of a controller on firmware 4.6.1 would."""
    self.name = "Test JellyFish"
    self.hostname = HOSTNAME
    self.version = "4.6.1"
    self.zones = ["Front", "Back"]
    self.states = {zone: JellyFishLightingZoneData(False) for zone in self.zones}
    self._controller_patterns = ["Christmas/Mint"]
    self._update_patterns()


async def fake_get_data_before_info(self):
    """A poll that finishes before the controller has reported its info."""
    await fake_get_data(self)
    self.name = None
    self.hostname = None


@pytest.fixture
async def setup_entry(hass, config_entry):
    with patch.object(JellyfishLightingApiClient, "async_get_data", fake_get_data):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        yield config_entry


async def test_device_reports_current_firmware(hass, setup_entry):
    # The config entry was created on 3.1.4; the controller now reports 4.6.1
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, HOSTNAME)})

    assert device.sw_version == "4.6.1"
    entities = er.async_entries_for_device(er.async_get(hass), device.id)
    assert len(entities) == 2


async def test_device_uses_saved_info_until_controller_reports_it(
    hass, config_entry
):
    with patch.object(
        JellyfishLightingApiClient, "async_get_data", fake_get_data_before_info
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    assert registry.async_get_device(identifiers={(DOMAIN, None)}) is None
    device = registry.async_get_device(identifiers={(DOMAIN, HOSTNAME)})
    assert device.name == "Test JellyFish"
    entities = er.async_entries_for_device(er.async_get(hass), device.id)
    assert len(entities) == 2
    assert config_entry.title == f"Test JellyFish ({HOSTNAME})"


async def test_only_stale_devices_can_be_removed(hass, setup_entry):
    registry = dr.async_get(hass)
    current = registry.async_get_device(identifiers={(DOMAIN, HOSTNAME)})
    stale = registry.async_get_or_create(
        config_entry_id=setup_entry.entry_id,
        identifiers={(DOMAIN, "JellyFish-OLD.local")},
    )

    assert await async_remove_config_entry_device(hass, setup_entry, stale)
    assert not await async_remove_config_entry_device(hass, setup_entry, current)


async def test_forget_action(hass, setup_entry):
    api = hass.data[DOMAIN][setup_entry.entry_id].api
    api._captured[PATTERN] = json.dumps(FIREWORKS)
    api._update_patterns()

    await hass.services.async_call(
        DOMAIN, "forget_captured_pattern", {"pattern": PATTERN}, blocking=True
    )

    assert PATTERN not in api.patterns
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "forget_captured_pattern", {"pattern": PATTERN}, blocking=True
        )


async def test_saved_pattern_cannot_be_forgotten(hass, setup_entry):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "forget_captured_pattern",
            {"pattern": "Christmas/Mint"},
            blocking=True,
        )


async def test_captured_patterns_loaded_on_setup(hass, hass_storage, config_entry):
    hass_storage[f"{DOMAIN}.captured_patterns.{config_entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.captured_patterns.{config_entry.entry_id}",
        "data": {PATTERN: json.dumps(FIREWORKS)},
    }
    with patch.object(JellyfishLightingApiClient, "async_get_data", fake_get_data):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("light.test_jellyfish_front")
    assert state.attributes["effect_list"] == ["Christmas/Mint", PATTERN]


async def test_removing_entry_deletes_captured_patterns(
    hass, hass_storage, setup_entry
):
    api = hass.data[DOMAIN][setup_entry.entry_id].api
    api._captured[PATTERN] = json.dumps(FIREWORKS)
    api._patterns_changed()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    key = f"{DOMAIN}.captured_patterns.{setup_entry.entry_id}"
    assert key in hass_storage

    await hass.config_entries.async_remove(setup_entry.entry_id)
    await hass.async_block_till_done()

    assert key not in hass_storage
