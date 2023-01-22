"""Switch platform for jellyfish-lighting."""
import re
import logging
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.light import (
    LightEntity,
    LightEntityFeature,
    ColorMode,
    ATTR_EFFECT,
)
from .const import DOMAIN
from . import JellyfishLightingDataUpdateCoordinator, JellyfishLightingApiClient
from .entity import JellyfishLightingEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup light platform"""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    lights = [
        JellyfishLightingLight(coordinator, entry, zone)
        for zone in coordinator.api.zones
    ]
    async_add_devices(lights)


class JellyfishLightingLight(JellyfishLightingEntity, LightEntity):
    """jellyfish-lighting light class."""

    def __init__(
        self,
        coordinator: JellyfishLightingDataUpdateCoordinator,
        entry: ConfigEntry,
        zone: str,
    ) -> None:
        """Initialize."""
        self._attr_supported_features = LightEntityFeature.EFFECT
        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self.api: JellyfishLightingApiClient = coordinator.api
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_icon = "mdi:led-strip-variant"
        self._attr_assumed_state = False
        self.zone = zone
        self.uid = re.sub("[^a-z0-9]", "_", zone.lower().strip("_"))
        self._attr_has_entity_name = True
        self._attr_name = zone
        self._attr_is_on = False
        self._attr_effect = None
        super().__init__(coordinator, entry)

    @property
    def unique_id(self):
        return self.uid

    @property
    def effect_list(self):
        return self.api.patterns

    async def async_added_to_hass(self) -> None:
        self._handle_coordinator_update()
        return await super().async_added_to_hass()

    async def async_refresh_data(self):
        """Refresh data for this entity"""
        await self.api.async_get_zone_data([self.zone])
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self, *args) -> None:
        """Handle updated data from the coordinator."""
        state = self.api.states[self.zone]
        self._attr_is_on = state[0] == 1
        self._attr_effect = state[1]

        _LOGGER.debug(
            "Updated state for %s (state: %s, effect: %s)",
            self.zone,
            "ON" if self._attr_is_on else "OFF",
            self._attr_effect,
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the light."""
        _LOGGER.debug("In async_turn_on for '%s'. kwargs is %s", self.zone, kwargs)
        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs.get(ATTR_EFFECT)

        _LOGGER.debug(
            "Turning on %s (effect: %s, color: %s, brightness: %s)",
            self.zone,
            self._attr_effect,
            self._attr_rgb_color,
            self._attr_brightness,
        )
        if self._attr_effect is not None:
            await self.api.async_play_pattern(self._attr_effect, [self.zone])
        else:
            await self.api.async_turn_on([self.zone])
        await self.async_refresh_data()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn off the light."""
        _LOGGER.debug("In async_turn_off for '%s'. kwargs is %s", self.zone, kwargs)
        await self.api.async_turn_off([self.zone])
        await self.async_refresh_data()
