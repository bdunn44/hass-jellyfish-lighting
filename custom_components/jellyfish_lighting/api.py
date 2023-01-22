"""Sample API Client."""
import logging
from typing import List, Dict, Tuple
from threading import Lock
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
        self._reconnect = False
        # two connections improves responsiveness for entity controls if actions are done during a scheduled update
        self._interval_controller = JellyFishLightingController(host)
        self._entity_controller = JellyFishLightingController(host)
        self.zones = None
        self.states = None
        self.patterns = None

    async def async_get_data(self):
        """Get data from the API."""
        try:
            _LOGGER.debug("Getting refreshed data for JellyFish Lighting")

            # Get data
            await self._hass.async_add_executor_job(
                self._interval_controller.getAndStoreZones
            )
            await self._hass.async_add_executor_job(
                self._interval_controller.getAndStorePatterns
            )

            # Check if zones have changed
            if self.zones is not None and set(self.zones) != set(
                self._interval_controller.zones
            ):
                # TODO: reload entities?
                pass

            # Get zones
            self.zones = self._interval_controller.zones
            _LOGGER.debug("Zones: %s", ", ".join(self.zones))

            # Get the list of available patterns/effects
            self.patterns = list(
                set(
                    [
                        p.toFolderAndName()
                        for p in self._interval_controller.patternFiles
                    ]
                )
            )
            self.patterns.sort()
            _LOGGER.debug("Patterns: %s", ", ".join(self.patterns))

            # Get the state of each zone
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
        try:
            _LOGGER.debug("Getting data for zone(s) %s", zones or "[all zones]")
            zones = zones or self.zones
            controller = (
                self._interval_controller
                if not zones or len(zones) > 1
                else self._entity_controller
            )
            for zone in zones:
                state = await self._hass.async_add_executor_job(
                    controller.getRunPattern, zone
                )
                if (
                    state.file == ""
                    and state.data
                    and state.data.numOfLeds == "Color"
                    and len(state.data.colors) == 3
                ):
                    # state is solid RGB
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
            msg = f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_on(self, zones: List[str] = None):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        try:
            _LOGGER.debug("Turning on zone(s) %s", zones or "[all zones]")
            await self._hass.async_add_executor_job(
                self._entity_controller.turnOn, zones
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to turn on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_turn_off(self, zones: List[str] = None):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        try:
            _LOGGER.debug("Turning off zone(s) %s", zones or "[all zones]")
            await self._hass.async_add_executor_job(
                self._entity_controller.turnOff, zones
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to connect to turn off JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_play_pattern(self, pattern: str, zones: List[str] = None):
        """Turn one or more zones on and applies a preset pattern. Affects all zones if zone list is None"""
        try:
            _LOGGER.debug(
                "Playing pattern '%s' on zone(s) %s",
                pattern,
                zones or "[all zones]",
            )
            await self._hass.async_add_executor_job(
                self._entity_controller.playPattern, pattern, zones
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to play pattern '{pattern}' on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    async def async_send_color(
        self, rgb: Tuple[int, int, int], brightness: int = 100, zones: List[str] = None
    ):
        """Turn one or more zones on and applies a preset pattern. Affects all zones if zone list is None"""
        try:
            _LOGGER.debug(
                "Sending color %s at %s brightness to zone(s) %s",
                rgb,
                brightness,
                zones or "[all zones]",
            )
            await self._hass.async_add_executor_job(
                self._entity_controller.sendColor, rgb, brightness, zones
            )
        except BaseException as ex:  # pylint: disable=broad-except
            msg = f"Failed to send color '{rgb}' on JellyFish Lighting zone(s) '{zones or '[all zones]'}'"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex


class JellyFishLightingController(jf.JellyFishController):
    """Wrapper for API to help with reconnections and thread safety"""

    def __init__(self, host: str) -> None:
        """Initialize API client."""
        self._host = host
        self._lock = Lock()
        self._reconnect = False
        super().__init__(host, True)

    def connect(self) -> None:
        try:
            with self._lock:
                # Connect/Reconnect
                if self._reconnect and super().connected:
                    _LOGGER.debug("Disconnecting from JellyFish Lighting controller")
                    super().disconnect()
                if not super().connected:
                    _LOGGER.debug("Connecting to JellyFish Lighting controller")
                    super().connect()
        except BaseException as ex:  # pylint: disable=broad-except
            self._reconnect = True
            msg = f"Failed to connect/reconnect to JellyFish Lighting controller at {self._host}"
            _LOGGER.exception(msg)
            raise Exception(msg) from ex

    def disconnect(self) -> None:
        with self._lock:
            super().disconnect()

    def getAndStoreZones(self) -> Dict:
        self.connect()
        with self._lock:
            return super().getAndStoreZones()

    def getAndStorePatterns(self) -> List[jf.PatternName]:
        self.connect()
        with self._lock:
            return super().getAndStorePatterns()

    def getRunPattern(self, zone: str = None) -> jf.RunPatternClass:
        self.connect()
        with self._lock:
            return super().getRunPattern(zone)

    def turnOn(self, zones: List[str] = None) -> None:
        self.connect()
        with self._lock:
            super().turnOn(zones)

    def turnOff(self, zones: List[str] = None) -> None:
        self.connect()
        with self._lock:
            super().turnOff(zones)

    def playPattern(self, pattern: str, zones: List[str] = None) -> None:
        self.connect()
        with self._lock:
            super().playPattern(pattern, zones)

    def sendColor(
        self, rgb: Tuple[int, int, int], brightness: int = 100, zones: List[str] = None
    ) -> None:
        self.connect()
        with self._lock:
            super().sendColor(rgb, brightness, zones)
