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
    ATTR_RGB_COLOR,
    ATTR_BRIGHTNESS,
)
from .const import DOMAIN
from . import JellyfishLightingDataUpdateCoordinator, JellyfishLightingApiClient
from .entity import JellyfishLightingEntity

_ALL_ZONES = "All Zones"
_DEFAULT_RGB = (255, 193, 7)
_DEFAULT_BRIGHTNESS = 255
_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup light platform"""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    lights = [
        JellyfishLightingLight(coordinator, entry, zone)
        for zone in coordinator.api.zones
    ]
    if len(lights) > 1:
        lights.insert(0, JellyfishLightingLight(coordinator, entry, _ALL_ZONES))
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
        self._attr_supported_color_modes = {ColorMode.RGB}
        self.api: JellyfishLightingApiClient = coordinator.api
        self._attr_color_mode = ColorMode.RGB
        self._attr_rgb_color = _DEFAULT_RGB
        self._attr_brightness = _DEFAULT_BRIGHTNESS
        self._attr_icon = "mdi:led-strip-variant"
        self._attr_assumed_state = False
        self.zone = zone
        self.api_zone = None if self.zone == _ALL_ZONES else [self.zone]
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
        await self.api.async_get_zone_data(self.api_zone)
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self, *args) -> None:
        if self.zone == _ALL_ZONES:
            ons = set()
            effects = set()
            colors = set()
            brightnesses = set()
            for state in self.api.states.values():
                ons.add(state[0])
                effects.add(state[1])
                colors.add(state[2])
                brightnesses.add(state[3])
            self._attr_is_on = len(ons) == 1 and ons.pop() == 1
            self._attr_effect = effects.pop() if len(effects) == 1 else None
            self._attr_rgb_color = colors.pop() if len(colors) == 1 else None
            self._attr_brightness = (
                brightnesses.pop() if len(brightnesses) == 1 else None
            )
        else:
            state = self.api.states[self.zone]
            self._attr_is_on = state[0] == 1
            self._attr_effect = state[1]
            self._attr_rgb_color = state[2]
            self._attr_brightness = state[3]

        if self._attr_brightness is None:
            self._attr_brightness = 255
        else:
            self._attr_brightness = int(self._attr_brightness / 100 * 255)

        _LOGGER.debug(
            "Updated state for %s (state: %s, effect: %s, color: %s, brightness: %s)",
            self.zone,
            "ON" if self._attr_is_on else "OFF",
            self._attr_effect,
            self._attr_rgb_color,
            self._attr_brightness,
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the light."""
        _LOGGER.debug("In async_turn_on for '%s'. kwargs is %s", self.zone, kwargs)
        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs.get(ATTR_EFFECT)
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = kwargs.get(ATTR_RGB_COLOR)
            self._attr_effect = None
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs.get(ATTR_BRIGHTNESS)
            self._attr_effect = None

        if self._attr_rgb_color is None:
            self._attr_rgb_color = _DEFAULT_RGB
        if self._attr_brightness is None:
            self._attr_brightness = _DEFAULT_BRIGHTNESS

        _LOGGER.debug(
            "Turning on %s (effect: %s, color: %s, brightness: %s)",
            self.zone,
            self._attr_effect,
            self._attr_rgb_color,
            self._attr_brightness,
        )
        if self._attr_effect is not None:
            await self.api.async_play_pattern(self._attr_effect, self.api_zone)
        elif self._attr_rgb_color is not None:
            await self.api.async_play_color(
                self._attr_rgb_color,
                int(self._attr_brightness / 255 * 100),
                self.api_zone,
            )
        else:
            await self.api.async_turn_on(self.api_zone)
        await self.async_refresh_data()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn off the light."""
        _LOGGER.debug("In async_turn_off for '%s'. kwargs is %s", self.zone, kwargs)
        await self.api.async_turn_off(self.api_zone)
        await self.async_refresh_data()
