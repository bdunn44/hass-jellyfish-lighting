"""Sample API Client."""
import logging
from typing import List
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import jellyfishlightspy as jf

_LOGGER: logging.Logger = logging.getLogger(__package__)


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
        self.zones = None
        self.states = None
        self.patterns = None

    async def connect(self):
        """Establish connection to the controller"""
        try:
            if not self._controller.connected:
                _LOGGER.debug(
                    "Connecting to the JellyFish Lighting controller at %s", self.host
                )
                await self._hass.async_add_executor_job(self._controller.connect)
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to JellyFish Lighting controller at {self.host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_get_data(self):
        """Get data from the API."""
        await self.connect()
        try:
            _LOGGER.debug("Getting refreshed data for JellyFish Lighting")

            # Get patterns
            patterns = await self._hass.async_add_executor_job(
                self._controller.getPatternList
            )
            self.patterns = [p.toFolderAndName() for p in patterns]
            self.patterns.sort()
            _LOGGER.debug("Patterns: %s", ", ".join(self.patterns))

            # Get Zones
            zones = await self._hass.async_add_executor_job(self._controller.getZones)

            # Check if zones have changed
            if self.zones is not None and set(self.zones) != set(list(zones)):
                # TODO: reload entities?
                pass

            self.zones = list(zones)
            _LOGGER.debug("Zones: %s", ", ".join(self.zones))

            # Get the state of all zones
            self.states = {}
            await self.async_get_zone_data()
            _LOGGER.debug("States: %s", self.states)
        except BaseException as ex:  # pylint: disable=broad-except
            msg = (
                f"Failed to get data from JellyFish Lighting controller at {self.host}"
            )
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_get_zone_data(self, zones: List[str] = None):
        """Retrieves and stores updated state data for one or more zones.
        Retrieves data for all zones if zone list is None"""
        await self.connect()
        try:
            _LOGGER.debug("Getting data for zone(s) %s", zones or "[all zones]")
            zones = list(set(zones or self.zones))
            states = await self._hass.async_add_executor_job(
                self._controller.getRunPatterns, zones
            )
            for zone, state in states.items():
                self.states[zone] = (
                    state.state,
                    state.file if state.file != "" else None,
                )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_on(self, zone: str):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        await self.connect()
        try:
            _LOGGER.debug("Turning on zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turnOn, [zone])
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to turn on JellyFish Lighting zone '{zone}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_off(self, zone: str):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        await self.connect()
        try:
            _LOGGER.debug("Turning off zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turnOff, [zone])
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to turn off JellyFish Lighting zone '{zone}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_play_pattern(self, pattern: str, zone: str):
        """Turn one or more zones on and applies a preset pattern. Affects all zones if zone list is None"""
        await self.connect()
        try:
            _LOGGER.debug("Playing pattern '%s' on zone %s", pattern, zone)
            await self._hass.async_add_executor_job(
                self._controller.playPattern, pattern, [zone]
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play pattern '{pattern}' on JellyFish Lighting zone '{zone}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex
