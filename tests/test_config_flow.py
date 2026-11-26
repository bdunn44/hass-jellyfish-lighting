"""Tests for the config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from jellyfishlightspy import JellyFishException

from custom_components.jellyfish_lighting.api import JellyfishLightingApiClient
from custom_components.jellyfish_lighting.const import (
    CONF_ADDRESS,
    CONF_HOSTNAME,
    CONF_NAME,
    CONF_VERSION,
    DOMAIN,
)

from .conftest import ADDRESS, FIREWORKS, HOSTNAME, push, run_pattern_message


async def fake_controller_info(self):
    self.name = "Test JellyFish"
    self.hostname = HOSTNAME
    self.version = "4.6.1"


async def start_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_flow_creates_entry(hass):
    result = await start_flow(hass)
    with (
        patch.object(JellyfishLightingApiClient, "async_connect", AsyncMock()),
        patch.object(
            JellyfishLightingApiClient,
            "async_get_controller_info",
            fake_controller_info,
        ),
        patch.object(JellyfishLightingApiClient, "async_disconnect", AsyncMock()),
        patch(
            "custom_components.jellyfish_lighting.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Test JellyFish",
        CONF_HOSTNAME: HOSTNAME,
        CONF_VERSION: "4.6.1",
    }


async def test_user_flow_cannot_connect(hass):
    result = await start_flow(hass)
    with patch.object(
        JellyfishLightingApiClient,
        "async_connect",
        AsyncMock(side_effect=JellyFishException("unreachable")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_client_without_entry_handles_pushes(hass):
    """The config flow's client has no entry, but the controller still pushes
    zone states and app patterns while it's connected."""
    api = JellyfishLightingApiClient(ADDRESS, None, hass)
    await api.async_load_captured_patterns()

    pattern = "Halloween/Candy Corn Fireworks"
    await push(hass, api, run_pattern_message(pattern, FIREWORKS))

    assert pattern in api.patterns
    assert api.states["Front"].is_on
