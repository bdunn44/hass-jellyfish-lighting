"""Sample API Client."""
from typing import List, Tuple, Dict
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from jellyfishlightspy import JellyFishController, JellyFishException, ZoneState
from .const import LOGGER


class JellyfishLightingApiClient:
    """API Client for JellyFish Lighting"""

    def __init__(
        self, host: str, config_entry: ConfigEntry, hass: HomeAssistant
    ) -> None:
        """Initialize API client."""
        self.host = host
        self._config_entry = config_entry
        self._hass = hass
        self._controller = JellyFishController(host)
        self.zones: List[str] = []
        self.states: Dict[str, JellyFishLightingZoneData] = {}
        self.patterns: List[str] = []

    async def async_connect(self):
        """Establish connection to the controller"""
        try:
            if not self._controller.connected:
                LOGGER.debug(
                    "Connecting to the JellyFish Lighting controller at %s", self.host
                )
                await self._hass.async_add_executor_job(self._controller.connect, 5)
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to connect to JellyFish Lighting controller at {self.host}"
            ) from ex

    async def async_get_data(self):
        """Get data from the API."""
        await self.async_connect()
        try:
            LOGGER.debug("Getting refreshed data from JellyFish Lighting controller")

            # Get patterns
            patterns = await self._hass.async_add_executor_job(
                self._controller.get_pattern_names
            )
            patterns.sort()
            self.patterns = patterns
            LOGGER.debug("Patterns: %s", ", ".join(self.patterns))

            # Get Zones
            zones = await self._hass.async_add_executor_job(
                self._controller.get_zone_names
            )

            # Check if zones have changed
            if self.zones is not None and set(self.zones) != set(list(zones)):
                # TODO: reload entities?
                pass

            self.zones = zones
            LOGGER.debug("Zones: %s", ", ".join(self.zones))

            # Get the state of all zones
            await self.async_get_zone_states()
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get data from JellyFish Lighting controller at {self.host}"
            ) from ex

    async def async_get_zone_states(self, zones: List[str] = None):
        """Retrieves and stores updated state data for one or more zones.
        Retrieves data for all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Getting data for zone(s) %s", zones or "[all zones]")
            states = await self._hass.async_add_executor_job(
                self._controller.get_zone_states, zones or self.zones
            )
            for zone, state in states.items():
                data = JellyFishLightingZoneData.from_zone_state(state)
                self.states[zone] = data
                LOGGER.debug("%s: %s", zone, data)
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.host}"
            ) from ex

    async def async_turn_on(self, zone: str):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning on zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turn_on, [zone])
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to turn on JellyFish Lighting zone '{zone}'"
            ) from ex

    async def async_turn_off(self, zone: str):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning off zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turn_off, [zone])
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to turn off JellyFish Lighting zone '{zone}'"
            ) from ex

    async def async_apply_pattern(self, pattern: str, zone: str):
        """Turn one or more zones on and apply a preset pattern. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Playing pattern '%s' on zone %s", pattern, zone)
            await self._hass.async_add_executor_job(
                self._controller.apply_pattern, pattern, [zone]
            )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to play pattern '{pattern}' on JellyFish Lighting zone '{zone}'"
            ) from ex

    async def async_apply_color(
        self, rgb: Tuple[int, int, int], brightness: int, zone: str
    ):
        """Turn one or more zones on and set all lights to a single color at the given brightness.
        Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug(
                "Applying color %s at %s brightness to zone %s",
                rgb,
                brightness,
                zone,
            )
            await self._hass.async_add_executor_job(
                self._controller.apply_color, rgb, brightness, [zone]
            )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to play color '{rgb}' at {brightness}% brightness on JellyFish Lighting zone '{zone}'"
            ) from ex


class JellyFishLightingZoneData:
    """Simple class to store the state of a zone"""

    def __init__(
        self,
        is_on: bool = None,
        file: str = None,
        color: tuple[int, int, int] = None,
        brightness: int = None,
    ):
        self.is_on = is_on
        self.file = file
        self.color = color
        self.brightness = brightness

    @classmethod
    def from_zone_state(cls, state: ZoneState):
        """Instantiates the class from the data returned by the API"""
        data = cls(state.is_on, state.file or None)
        if state.data:
            data.brightness = state.data.runData.brightness
            if state.data.type == "Color" and len(state.data.colors) == 3:
                data.color = tuple(state.data.colors)
        return data

    def __repr__(self) -> str:
        return str(vars(self))
