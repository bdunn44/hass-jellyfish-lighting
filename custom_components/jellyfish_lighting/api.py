"""Sample API Client."""
import logging
from typing import List
from asyncio import Lock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import jellyfishlightspy as jf

TIMEOUT = 10
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
        self._lock = Lock()
        self._reconnect = False
        self._controller = jf.JellyFishController(host, True)
        self.zones = None
        self.states = None
        self.patterns = None

    async def async_connect(self):
        """Connect/reconnect to the JellyFish controller"""
        try:
            async with self._lock:
                # Connect/Reconnect
                if self._reconnect and self._controller.connected:
                    _LOGGER.debug("Disconnecting from JellyFish Lighting controller")
                    await self._hass.async_add_executor_job(self._controller.disconnect)
                if not self._controller.connected:
                    _LOGGER.debug("Connecting to JellyFish Lighting controller")
                    await self._hass.async_add_executor_job(self._controller.connect)
        except BaseException as ex:  # pylint: disable=broad-except
            self._reconnect = True
            msg = f"Failed to connect/reconnect to JellyFish Lighting controller at {self.host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_get_data(self):
        """Get data from the API."""
        try:
            await self.async_connect()
            async with self._lock:
                _LOGGER.debug("Getting refreshed data for JellyFish Lighting")

                # Get data
                await self._hass.async_add_executor_job(
                    self._controller.getAndStoreZones
                )
                await self._hass.async_add_executor_job(
                    self._controller.getAndStorePatterns
                )

                # Check if zones have changed
                if self.zones is not None and set(self.zones) != set(
                    self._controller.zones
                ):
                    # TODO: reload entities
                    pass

                # Get zones
                self.zones = self._controller.zones
                _LOGGER.debug("Zones: %s", ", ".join(self.zones))

                # Get the list of available patterns/effects
                self.patterns = list(
                    set([p.toFolderAndName() for p in self._controller.patternFiles])
                )
                self.patterns.sort()
                # _LOGGER.debug("Patterns: %s", ", ".join(self.patterns))

            # Get the state of each zone
            self.states = {}
            await self.async_get_zone_data()
            _LOGGER.debug("States: %s", self.states)
        except BaseException as ex:  # pylint: disable=broad-except
            self._reconnect = True
            msg = (
                f"Failed to get data from JellyFish Lighting controller at {self.host}"
            )
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_get_zone_data(self, zones: List[str] = None):
        """Retrieves and stores updated state data for one or more zones.
        Retrieves data for all zones if zone list is None"""
        try:
            async with self._lock:
                zones = zones or self.zones
                for zone in zones:
                    state = await self._hass.async_add_executor_job(
                        self._controller.getRunPattern, zone
                    )
                    # Check if state is solid RGB
                    if (
                        state.file == ""
                        and state.data.numOfLeds == "Color"
                        and state.data.runData == "No Color Transform"
                        and state.data.colorPos.effect == "No Effect"
                        and len(state.data.colors) == 3
                    ):
                        self.states[zone] = (
                            state.state,
                            None,
                            tuple(state.data.colors),
                            state.data.colorPos.brightness,
                        )
                    else:
                        self.states[zone] = (
                            state.state,
                            state.file if state.file != "" else None,
                            None,
                            None,
                        )
        except BaseException as ex:  # pylint: disable=broad-except
            self._reconnect = True
            msg = f"Failed to get zone data from JellyFish Lighting controller at {self.host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_on(self, zones: List[str] = None):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        try:
            async with self._lock:
                _LOGGER.debug("Turning on zone(s) %s", zones or "[all zones]")
                await self._hass.async_add_executor_job(self._controller.turnOn, zones)
                self._reconnect = True  # hacky, but avoids intermittent multi-repsonse issues w/ websocket
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to turn on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_off(self, zones: List[str] = None):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        try:
            async with self._lock:
                _LOGGER.debug("Turning off zone(s) %s", zones or "[all zones]")
                await self._hass.async_add_executor_job(self._controller.turnOff, zones)
                self._reconnect = True  # hacky, but avoids intermittent multi-repsonse issues w/ websocket
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to turn off JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_play_pattern(self, pattern: str, zones: List[str] = None):
        """Turn one or more zones on and applies a preset pattern. Affects all zones if zone list is None"""
        try:
            async with self._lock:
                _LOGGER.debug(
                    "Playing pattern '%s' on zone(s) %s",
                    pattern,
                    zones or "[all zones]",
                )
                await self._hass.async_add_executor_job(
                    self._controller.playPattern, pattern, zones
                )
                self._reconnect = True  # hacky, but avoids intermittent multi-repsonse issues w/ websocket
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play pattern '{pattern}' on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_play_color(
        self, rgb: tuple, brightness: int, zones: List[str] = None
    ):
        """Turn one or more zones on and sets the color of all lights. Affects all zones if zone list is None"""
        try:
            async with self._lock:
                _LOGGER.debug(
                    "Playing color '%s' at %s pct brightness on zone(s) %s",
                    rgb,
                    brightness,
                    zones or "[all zones]",
                )
                await self._hass.async_add_executor_job(
                    self._controller.sendColor, rgb, brightness, zones
                )
                self._reconnect = True  # hacky, but avoids intermittent multi-repsonse issues w/ websocket
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play color '{rgb}' at brightness {brightness} on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex
