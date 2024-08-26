"""Sample API Client."""

import asyncio
from typing import List, Tuple, Dict
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from jellyfishlightspy import (
    JellyFishController,
    JellyFishException,
    ZoneState,
    NAME_DATA,
    HOSTNAME_DATA,
    FIRMWARE_VERSION_DATA,
    ZONE_CONFIG_DATA,
    PATTERN_LIST_DATA,
    PATTERN_CONFIG_DATA,
    ZONE_STATE_DATA,
)
from .const import LOGGER, DOMAIN


class JellyfishLightingApiClient:
    """API Client for JellyFish Lighting"""

    def __init__(
        self, address: str, config_entry: ConfigEntry, hass: HomeAssistant
    ) -> None:
        """Initialize API client."""
        self.address = address
        self._config_entry = config_entry
        self._hass = hass
        self._controller = JellyFishController(address)
        self._connecting = asyncio.Lock()
        self.zones: List[str] = []
        self.states: Dict[str, JellyFishLightingZoneData] = {}
        self.patterns: List[str] = []
        self.name: str = None
        self.hostname: str = None
        self.version: str = None
        self._controller.add_listener(
            on_message=self._recieve_push, on_error=self._attempt_reconnect
        )

    @property
    def _coord(self) -> DataUpdateCoordinator:
        return self._hass.data[DOMAIN][self._config_entry.entry_id]

    @property
    def connecting(self) -> bool:
        """Indicates whether the client is currently attempting to connect to the controller"""
        return self._connecting.locked()

    @property
    def connected(self) -> bool:
        """Indicates whether the client is connected to the controller"""
        return self._controller.connected

    def register_push_listener(self, entity: CoordinatorEntity) -> None:
        """Adds a listener that is called when push events are received from the controller"""

        def listener(*args):
            async def update():
                entity.schedule_update_ha_state(force_refresh=False)

            asyncio.run_coroutine_threadsafe(update(), self._hass.loop)
            # self._hass.async_create_task(update())
            # self._hass.loop.create_task(entity.async_write_ha_state())
            # self._hass.async_create_task(entity.async_write_ha_state)
            # asyncio.run_coroutine_threadsafe(
            #     entity.async_write_ha_state(), self._hass.loop
            # )

        self._controller.add_listener(
            on_open=listener,
            on_close=listener,
            on_message=listener,
            on_error=listener,
        )

    def _attempt_reconnect(self, *args) -> None:
        """Attempts to reconnect to the controller"""
        asyncio.run_coroutine_threadsafe(self.async_connect(), self._hass.loop)

    def _recieve_push(self, data):
        """Updates state data when a push event is received from the controller"""

        async def update():
            if NAME_DATA in data:
                self.name = self._controller.name
                LOGGER.debug("[PUSH UPDATE] Name: %s", self.name)
            elif HOSTNAME_DATA in data:
                self.hostname = self._controller.hostname
                LOGGER.debug("[PUSH UPDATE] Hostname: %s", self.hostname)
            elif FIRMWARE_VERSION_DATA in data:
                self.version = self._controller.firmware_version.ver
                LOGGER.debug("[PUSH UPDATE] Version: %s", self.version)
            elif ZONE_CONFIG_DATA in data:
                self.zones = self._controller.zone_names
                LOGGER.debug("[PUSH UPDATE] Zones: %s", ", ".join(self.zones))
            elif PATTERN_LIST_DATA in data or PATTERN_CONFIG_DATA in data:
                patterns = self._controller.pattern_names
                patterns.sort()
                self.patterns = patterns
                LOGGER.debug("[PUSH UPDATE] Patterns: %s", ", ".join(self.patterns))
            elif ZONE_STATE_DATA in data:
                for zone, state in self._controller.zone_states.items():
                    if not state:
                        continue
                    state = JellyFishLightingZoneData.from_zone_state(state)
                    self.states[zone] = state
                    LOGGER.debug("[PUSH UPDATE] '%s' State: %s", zone, state)
            self._coord.async_set_updated_data(data)

        asyncio.run_coroutine_threadsafe(update(), self._hass.loop)

    async def async_connect(self):
        """Establish connection to the controller"""
        if self.connected or self.connecting:
            return
        try:
            async with self._connecting:
                LOGGER.debug(
                    "Connecting to the JellyFish Lighting controller at %s",
                    self.address,
                )
                await self._hass.async_add_executor_job(self._controller.connect, 5)
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to connect to JellyFish Lighting controller at {self.address}"
            ) from ex

    async def async_disconnect(self):
        """Disconnects from the controller"""
        if not self.connected:
            return
        try:
            async with self._connecting:
                LOGGER.debug(
                    "Disconnecting from the JellyFish Lighting controller at %s",
                    self.address,
                )
                await self._hass.async_add_executor_job(self._controller.disconnect, 5)
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to disconnect from JellyFish Lighting controller at {self.address}"
            ) from ex

    async def async_get_data(self):
        """Manually fetches data from the controller."""
        await self.async_connect()
        try:
            LOGGER.debug("Getting refreshed data from JellyFish Lighting controller")
            await self.async_get_controller_info()
            await self._hass.async_add_executor_job(self._controller.get_pattern_names)
            await self._hass.async_add_executor_job(self._controller.get_zone_names)
            await self.async_get_zone_states()
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get data from JellyFish Lighting controller at {self.address}"
            ) from ex

    async def async_get_controller_info(self):
        """Retrieves basic information from the controller"""
        try:
            await self._hass.async_add_executor_job(self._controller.get_name)
            await self._hass.async_add_executor_job(self._controller.get_hostname)
            await self._hass.async_add_executor_job(
                self._controller.get_firmware_version
            )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to retrieve JellyFish controller information from {self.address}"
            ) from ex

    async def async_get_zone_states(self, zone: str = None):
        """Retrieves and stores updated state data for one or more zones.
        Retrieves data for all zones if zone list is None"""
        await self.async_connect()
        try:
            zones = [zone] if zone else self.zones
            LOGGER.debug("Getting data for zone(s) %s", zones or "[all zones]")
            await self._hass.async_add_executor_job(
                self._controller.get_zone_states, zones
            )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.address}"
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
            LOGGER.debug("Applying pattern '%s' to zone %s", pattern, zone)
            await self._hass.async_add_executor_job(
                self._controller.apply_pattern, pattern, [zone]
            )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to apply pattern '{pattern}' on JellyFish Lighting zone '{zone}'"
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
                f"Failed to apply color '{rgb}' at {brightness}% brightness on JellyFish Lighting zone '{zone}'"
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
