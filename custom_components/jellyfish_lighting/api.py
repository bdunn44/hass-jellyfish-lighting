"""Sample API Client."""
import asyncio
from typing import List, Tuple, Dict
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import jellyfishlightspy as jf
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
        self._controller = jf.JellyFishController(host, False)
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
                await asyncio.wait_for(
                    self._hass.async_add_executor_job(self._controller.connect),
                    timeout=5,
                )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to JellyFish Lighting controller at {self.host}"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_get_data(self):
        """Get data from the API."""
        await self.async_connect()
        try:
            LOGGER.debug("Getting refreshed data for JellyFish Lighting")

            # Get patterns
            patterns = await self._hass.async_add_executor_job(
                self._controller.getPatternList
            )
            self.patterns = [p.toFolderAndName() for p in patterns]
            self.patterns.sort()
            LOGGER.debug("Patterns: %s", ", ".join(self.patterns))

            # Get Zones
            zones = await self._hass.async_add_executor_job(self._controller.getZones)

            # Check if zones have changed
            if self.zones is not None and set(self.zones) != set(list(zones)):
                # TODO: reload entities?
                pass

            self.zones = list(zones)
            LOGGER.debug("Zones: %s", ", ".join(self.zones))

            # Get the state of all zones
            await self.async_get_zone_data()
        except BaseException as ex:  # pylint: disable=broad-except
            msg = (
                f"Failed to get data from JellyFish Lighting controller at {self.host}"
            )
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_get_zone_data(self, zones: List[str] = None):
        """Retrieves and stores updated state data for one or more zones.
        Retrieves data for all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Getting data for zone(s) %s", zones or "[all zones]")
            zones = list(set(zones or self.zones))
            states = await self._hass.async_add_executor_job(
                self._controller.getRunPatterns, zones
            )

            for zone, state in states.items():
                if zone not in self.states:
                    self.states[zone] = JellyFishLightingZoneData()
                data = self.states[zone]
                if (
                    state.file == ""
                    and state.data
                    and state.data.numOfLeds == "Color"
                    and len(state.data.colors) == 3
                ):
                    # state is solid RGB
                    data.state = state.state
                    data.file = None
                    data.color = tuple(state.data.colors)
                    data.brightness = state.data.colorPos.brightness
                else:
                    data.state = state.state
                    data.file = state.file if state.file != "" else None
                    data.color = None
                    data.brightness = None

                LOGGER.debug("%s: (%s)", zone, data)
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.host}"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_turn_on(self, zone: str):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning on zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turnOn, [zone])
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to turn on JellyFish Lighting zone '{zone}'"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_turn_off(self, zone: str):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning off zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turnOff, [zone])
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to turn off JellyFish Lighting zone '{zone}'"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_play_pattern(self, pattern: str, zone: str):
        """Turn one or more zones on and apply a preset pattern. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Playing pattern '%s' on zone %s", pattern, zone)
            await self._hass.async_add_executor_job(
                self._controller.playPattern, pattern, [zone]
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play pattern '{pattern}' on JellyFish Lighting zone '{zone}'"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised

    async def async_send_color(
        self, rgb: Tuple[int, int, int], brightness: int, zone: str
    ):
        """Turn one or more zones on and set all lights to a single color at the given brightness.
        Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug(
                "Playing color %s at %s brightness to zone(s) %s",
                rgb,
                brightness,
                zone,
            )
            await self._hass.async_add_executor_job(
                self._controller.sendColor, rgb, brightness, zone
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play color '{rgb}' at {brightness}% brightness on JellyFish Lighting zone '{zone}'"
            LOGGER.exception(msg)
            raise Exception(msg) from ex  # pylint: disable=broad-exception-raised


class JellyFishLightingZoneData:
    """Simple class to store the state of a zone"""

    def __init__(
        self,
        state: bool = None,
        file: str = None,
        color: tuple[int, int, int] = None,
        brightness: int = None,
    ):
        self.state = state
        self.file = file
        self.color = color
        self.brightness = brightness

    def __str__(self) -> str:
        return f"state: {self.state}, file: {self.file}, color: {self.color}, brightness: {self.brightness}"
