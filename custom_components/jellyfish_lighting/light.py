"""Switch platform for jellyfish-lighting."""

import re
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.light import (
    LightEntity,
    LightEntityFeature,
    ColorMode,
    ATTR_EFFECT,
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
)
from .const import (
    LOGGER,
    DOMAIN,
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR,
)
from . import JellyfishLightingDataUpdateCoordinator, JellyfishLightingApiClient
from .entity import JellyfishLightingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup light platform"""
    coord = hass.data[DOMAIN][entry.entry_id]
    lights = [JellyfishLightingLight(coord, entry, zone) for zone in coord.api.zones]
    async_add_entities(lights)


class JellyfishLightingLight(JellyfishLightingEntity, LightEntity):
    """jellyfish-lighting light class."""

    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_icon = "mdi:led-strip-variant"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JellyfishLightingDataUpdateCoordinator,
        entry: ConfigEntry,
        zone: str,
    ) -> None:
        """Initialize."""
        self.api: JellyfishLightingApiClient = coordinator.api
        self.zone = zone
        self._attr_unique_id = re.sub("[^a-z0-9]", "_", zone.lower().strip("_"))
        self._attr_name = zone
        self._attr_is_on = False
        self._attr_effect = None
        self.api.register_push_listener(self)
        super().__init__(coordinator, entry)

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        try:
            self.api.states[self.zone]
        except KeyError:
            return False
        return self.api.connected

    @property
    def effect_list(self) -> list[str]:
        """Return the list of supported effects."""
        return self.api.patterns

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        return self.api.states[self.zone].is_on

    @property
    def effect(self) -> str | None:
        """Return the current effect of the light."""
        return self.api.states[self.zone].file

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the color value."""
        return self.api.states[self.zone].color or DEFAULT_COLOR

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        brightness = self.api.states[self.zone].brightness or DEFAULT_BRIGHTNESS
        # JF API returns brightness as an int between 0 and 100
        return int(brightness / 100 * 255)

    async def async_added_to_hass(self) -> None:
        self._handle_coordinator_update()
        return await super().async_added_to_hass()

    async def async_refresh_data(self):
        """Refresh data for this entity"""
        await self.api.async_get_zone_states(self.zone)
        self._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the zone."""
        effect = kwargs.get(ATTR_EFFECT)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        LOGGER.debug(
            "Turning on %s (effect: %s, color: %s, brightness: %s)",
            self.zone,
            effect,
            rgb_color,
            brightness,
        )
        if effect:
            await self.api.async_apply_pattern(effect, self.zone)
        elif rgb_color or brightness:
            # Fill in the blanks (kwargs only contains changed attributes)
            # Convert brightness back to a 0..100 value
            brightness = int((brightness or self.brightness) / 255 * 100)
            rgb_color = rgb_color or self.rgb_color
            await self.api.async_apply_color(rgb_color, brightness, self.zone)
        else:
            await self.api.async_turn_on(self.zone)
        await self.async_refresh_data()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the zone."""
        LOGGER.debug("Turning off zone '%s'", self.zone)
        await self.api.async_turn_off(self.zone)
        await self.async_refresh_data()
