"""
Custom integration to integrate JellyFish Lighting with Home Assistant.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry

from .api import JellyfishLightingApiClient

from .const import (
    LOGGER,
    SCAN_INTERVAL,
    CONF_ADDRESS,
    DOMAIN,
    NAME,
    DEVICE,
    LIGHT,
    STARTUP_MESSAGE,
)


async def async_setup(
    hass: HomeAssistant, config: Config
):  # pylint: disable=unused-argument
    """Setting up this integration using YAML is not supported."""
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
    coordinator = JellyfishLightingDataUpdateCoordinator(hass, client=client)
    await coordinator.async_refresh()
    hass.config_entries.async_update_entry(
        entry, title=f"{client.name} ({client.hostname})"
    )

    if not coordinator.last_update_success:
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
    hass.async_add_job(hass.config_entries.async_forward_entry_setup(entry, LIGHT))

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


class JellyfishLightingDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, client: JellyfishLightingApiClient) -> None:
        """Initialize."""
        self.api = client
        self.platforms = []
        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.api.async_get_data()
        except Exception as exception:
            LOGGER.exception("Error fetching %s data", DOMAIN)
            raise UpdateFailed() from exception


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    LOGGER.info("Unloading JellyFish Lighting integration")
    # coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = await hass.config_entries.async_forward_entry_unload(entry, LIGHT)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    LOGGER.info("Reloading JellyFish Lighting integration")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
