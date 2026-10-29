"""
Custom integration to integrate JellyFish Lighting with Home Assistant.
"""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.core_config import Config
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry

from .api import JellyfishLightingApiClient, captured_patterns_store

from .const import (
    LOGGER,
    SCAN_INTERVAL,
    ATTR_PATTERN,
    SERVICE_FORGET_CAPTURED_PATTERN,
    CONF_ADDRESS,
    DOMAIN,
    NAME,
    DEVICE,
    LIGHT,
    STARTUP_MESSAGE,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(
    hass: HomeAssistant, config: Config
):  # pylint: disable=unused-argument
    """Setting up this integration using YAML is not supported."""

    async def forget_captured_pattern(call: ServiceCall) -> None:
        pattern = call.data[ATTR_PATTERN]
        forgotten = [
            coordinator.api.async_forget_captured_pattern(pattern)
            for coordinator in hass.data.get(DOMAIN, {}).values()
        ]
        if not any(forgotten):
            raise ServiceValidationError(
                f"'{pattern}' isn't a pattern captured from the JellyFish app"
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_CAPTURED_PATTERN,
        forget_captured_pattern,
        schema=vol.Schema({vol.Required(ATTR_PATTERN): cv.string}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    LOGGER.info("Setting up JellyFish Lighting integration")
    LOGGER.debug(
        "async_setup_entry config entry is: %s",
        {
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
            "domain": entry.domain,
            "title": entry.title,
            "data": entry.data,
        },
    )
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        LOGGER.info(STARTUP_MESSAGE)

    address = entry.data.get(CONF_ADDRESS)
    client = JellyfishLightingApiClient(address, entry, hass)
    await client.async_load_captured_patterns()
    coordinator = JellyfishLightingDataUpdateCoordinator(hass, client=client)
    await coordinator.async_refresh()
    # try:
    #     await client.async_get_data()
    # except Exception as e:
    #     LOGGER.exception("Error fetching %s data", DOMAIN)
    #     raise ConfigEntryNotReady from e
    hass.config_entries.async_update_entry(
        entry, title=f"{client.name} ({client.hostname})"
    )

    if not coordinator.last_update_success:
        # Each setup retry creates a new client, so close this one's connection
        try:
            await client.async_disconnect()
        except HomeAssistantError:
            pass
        raise ConfigEntryNotReady

    registry = device_registry.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client.hostname)},
        name=client.name,
        manufacturer=NAME,
        model=DEVICE,
        sw_version=client.version,
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [LIGHT])

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


class JellyfishLightingDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: JellyfishLightingApiClient) -> None:
        """Initialize."""
        self.api = client
        self.platforms = [LIGHT]
        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.api.async_get_data()
        except Exception as exception:
            # The coordinator logs the first failure and the recovery, so an
            # outage doesn't log a traceback on every poll
            raise UpdateFailed(str(exception)) from exception


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    LOGGER.info("Unloading JellyFish Lighting integration")
    unloaded = await hass.config_entries.async_forward_entry_unload(entry, LIGHT)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the WebSocket so a reload doesn't leave the old connection
        # (and its listener thread) running alongside the new one
        try:
            await coordinator.api.async_disconnect()
        except HomeAssistantError:
            LOGGER.warning("Failed to disconnect from the JellyFish controller")
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the patterns captured for an entry when it's removed."""
    await captured_patterns_store(hass, entry.entry_id).async_remove()


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    LOGGER.info("Reloading JellyFish Lighting integration")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
