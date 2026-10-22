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
        self._reconnecting = False
        self._closing = False
        self.zones: List[str] = []
        self.states: Dict[str, JellyFishLightingZoneData] = {}
        self.patterns: List[str] = []
        self.name: str = None
        self.hostname: str = None
        self.version: str = None
        self._controller.add_listener(
            on_message=self._recieve_push,
            on_error=self._attempt_reconnect,
            on_close=self._attempt_reconnect,
        )

    @property
    def _coord(self) -> DataUpdateCoordinator:
        # Returns None (rather than raising KeyError) if the coordinator has not
        # been stored in hass.data yet. The controller floods push data on
        # connect, which can fire _recieve_push before async_setup_entry has
        # finished registering the coordinator.
        return self._hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)

    @property
    def connecting(self) -> bool:
        """Indicates whether the client is currently attempting to connect to the controller"""
        return self._connecting.locked()

    @property
    def connected(self) -> bool:
        """Indicates whether the client is connected to the controller"""
        return self._controller.connected

    @property
    def reconnecting(self) -> bool:
        """Indicates whether a reconnect attempt is currently in progress"""
        return self._reconnecting

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
        """Schedules a reconnect after an unexpected disconnect.

        Wired to both on_error and on_close. The JellyFish controller closes
        idle WebSocket connections cleanly (on_close, no error), which is why
        entities silently went unavailable with nothing logged - the previous
        code only reconnected on_error. Skip when the disconnect is our own
        doing: an intentional disconnect, or the force-close that happens
        inside a connect / reconnect already in progress.
        """
        if self._closing or self._reconnecting or self.connecting or self.connected:
            return
        LOGGER.debug(
            "JellyFish controller at %s disconnected; scheduling reconnect",
            self.address,
        )
        self._reconnecting = True
        asyncio.run_coroutine_threadsafe(self._async_reconnect(), self._hass.loop)

    async def _async_reconnect(self):
        """Force-close stale connection and reconnect.

        The JellyFish controller only accepts one WebSocket connection at a
        time. If the previous connection's TCP socket is still ESTABLISHED at
        the kernel level (stale), new connection attempts will time out
        indefinitely. We must tear down the old connection first.
        """
        try:
            LOGGER.debug(
                "Force-closing stale connection to JellyFish controller at %s",
                self.address,
            )
            await self._hass.async_add_executor_job(self._force_close_connection)
            # Give the controller time to release the old session
            await asyncio.sleep(2)
            try:
                await self.async_connect()
            except HomeAssistantError:
                LOGGER.warning(
                    "Reconnect to JellyFish controller at %s failed, will retry on next poll",
                    self.address,
                )
        finally:
            self._reconnecting = False

    def _force_close_connection(self):
        """Force-close the underlying WebSocket and TCP connection."""
        # Grab the WebSocket object before disconnect() can set it to None.
        # WebSocket.close() has an early-exit guard (if not self.connected: return)
        # that skips socket teardown when the connection has already errored.
        # WebSocket.shutdown() has no such guard and directly closes the raw
        # TCP socket, which is what we need to release the controller's session.
        try:
            ws = self._controller._JellyFishController__ws
            if hasattr(ws, "sock") and ws.sock and hasattr(ws.sock, "shutdown"):
                ws.sock.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._controller.disconnect(timeout=3)
        except Exception:  # noqa: BLE001
            pass

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
            coord = self._coord
            if coord is not None:
                coord.async_set_updated_data(data)

        asyncio.run_coroutine_threadsafe(update(), self._hass.loop)

    async def async_connect(self):
        """Establish connection to the controller"""
        self._closing = False
        if self.connected or self.connecting:
            return
        try:
            async with self._connecting:
                # Force-close any stale connection before reconnecting.
                # The JellyFish controller only accepts one WebSocket at a
                # time, so a leftover TCP connection will block new ones.
                await self._hass.async_add_executor_job(self._force_close_connection)
                await asyncio.sleep(1)
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
        self._closing = True
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
        """Manually fetches data from the controller.

        Controller info, pattern names, and zone names are static config that
        the controller floods over the WebSocket on connect. Polling them
        explicitly on every 60s cycle races against that push flood and times
        out, which previously surfaced as UpdateFailed and marked the
        integration unavailable. We now only fetch each explicitly when it is
        still missing, treat timeouts as non-fatal, and let push keep them
        current.
        """
        await self.async_connect()
        try:
            LOGGER.debug("Getting refreshed data from JellyFish Lighting controller")
            if not self.name:
                try:
                    await self.async_get_controller_info()
                except HomeAssistantError:
                    LOGGER.debug(
                        "Could not fetch controller info from %s; "
                        "will retry on next poll or via push update",
                        self.address,
                    )
            if not self.patterns:
                try:
                    await self._hass.async_add_executor_job(
                        self._controller.get_pattern_names, 30
                    )
                except JellyFishException:
                    LOGGER.debug(
                        "Pattern names poll timed out for %s; will arrive via push update",
                        self.address,
                    )
            if not self.zones:
                try:
                    await self._hass.async_add_executor_job(
                        self._controller.get_zone_names, 30
                    )
                except JellyFishException:
                    LOGGER.debug(
                        "Zone names poll timed out for %s; will arrive via push update",
                        self.address,
                    )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get data from JellyFish Lighting controller at {self.address}"
            ) from ex
        # If polls timed out, wait for push to populate zones (controller floods on connect)
        if not self.zones:
            LOGGER.debug(
                "Zones not yet populated; waiting for push data from %s", self.address
            )
            for _ in range(30):
                await asyncio.sleep(1)
                if self.zones:
                    break
            if not self.zones:
                raise HomeAssistantError(
                    f"No zone data received from JellyFish controller at {self.address}"
                )
        try:
            await self.async_get_zone_states()
        except HomeAssistantError:
            LOGGER.debug(
                "Zone state poll timed out for %s; state is current via push updates",
                self.address,
            )

    async def async_get_controller_info(self):
        """Retrieves basic information from the controller"""
        try:
            await self._hass.async_add_executor_job(self._controller.get_name, 30)
            await self._hass.async_add_executor_job(self._controller.get_hostname, 30)
            await self._hass.async_add_executor_job(
                self._controller.get_firmware_version, 30
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
            zone_states = await self._hass.async_add_executor_job(
                self._controller.get_zone_states, zones, 30
            )
            for zone_name, state in zone_states.items():
                if not state:
                    continue
                self.states[zone_name] = JellyFishLightingZoneData.from_zone_state(state)

        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to get zone data for [{', '.join(zones)}] from JellyFish Lighting controller at {self.address}"
            ) from ex

    async def async_turn_on(self, zone: str):
        """Turn one or more zones on. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning on zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turn_on, [zone], False)
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to turn on JellyFish Lighting zone '{zone}'"
            ) from ex

    async def async_turn_off(self, zone: str):
        """Turn one or more zones off. Affects all zones if zone list is None"""
        await self.async_connect()
        try:
            LOGGER.debug("Turning off zone %s", zone)
            await self._hass.async_add_executor_job(self._controller.turn_off, [zone], False)
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
                self._controller.apply_pattern, pattern, [zone], False
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
                self._controller.apply_color, rgb, brightness, [zone], False
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
        is_on = getattr(state, "is_on", bool(state.state))
        data = cls(is_on, state.file or None)

        if state.data:
            data.brightness = state.data.runData.brightness
            if state.data.type == "Color" and len(state.data.colors) == 3:
                data.color = tuple(state.data.colors)
        return data

    def __repr__(self) -> str:
        return str(vars(self))
