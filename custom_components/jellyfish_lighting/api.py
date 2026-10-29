"""Sample API Client."""

import asyncio
import json
from typing import List, Tuple, Dict
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store
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
from jellyfishlightspy.requests import SetZoneStateRequest
from homeassistant.helpers import device_registry
from .const import LOGGER, DOMAIN

# Consecutive zone state polls with no response (and no push data in between)
# before the connection is assumed dead and forcibly re-established
MAX_MISSED_POLLS = 2

# Failed reconnect attempts before entities are reported unavailable. A brief
# blip shouldn't flap entities, but a controller that's gone shouldn't show
# stale state indefinitely.
MAX_FAILED_RECONNECTS = 2

# Upper bound (seconds) for the exponential backoff between reconnect attempts
MAX_RECONNECT_DELAY = 300

CAPTURED_PATTERNS_STORAGE_VERSION = 1


def captured_patterns_store(hass: HomeAssistant, entry_id: str) -> Store:
    """Storage for the patterns captured for a config entry"""
    return Store(
        hass,
        CAPTURED_PATTERNS_STORAGE_VERSION,
        f"{DOMAIN}.captured_patterns.{entry_id}",
    )


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
        self._missed_polls = 0
        self._failed_reconnects = 0
        self._refresh_static = False
        self.zones: List[str] = []
        self.states: Dict[str, JellyFishLightingZoneData] = {}
        # Effect list: patterns saved on the controller plus captured ones
        self.patterns: List[str] = []
        self._controller_patterns: List[str] = []
        # Patterns the JellyFish app ran that aren't saved on the controller
        # (e.g. its cloud library), as the raw pattern JSON it sent
        self._captured: Dict[str, str] = {}
        self._store = captured_patterns_store(hass, config_entry.entry_id)
        self.name: str = None
        self.hostname: str = None
        self.version: str = None
        self._controller.add_listener(
            on_message=self._recieve_push,
            on_error=self._attempt_reconnect,
            on_close=self._attempt_reconnect,
        )
        # The library parses runPattern data into a PatternConfig, which drops
        # settings it doesn't know (e.g. fireworkSettings), so capturing needs
        # the raw message. connect() reads on_message from the monitor each
        # time it creates the WebSocket, so wrapping it here covers reconnects.
        monitor = self._controller._JellyFishController__ws_monitor
        on_message = monitor.on_message

        def on_raw_message(ws, message):
            on_message(ws, message)
            self._capture_pattern(message)

        monitor.on_message = on_raw_message

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
    def available(self) -> bool:
        """Indicates whether entities should be reported as available.

        True while connected, or while a (re)connect is in progress and hasn't
        yet failed repeatedly, so a routine idle-close doesn't flap entities.
        """
        if self.connected:
            return True
        return (
            self.connecting or self._reconnecting
        ) and self._failed_reconnects < MAX_FAILED_RECONNECTS

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
        """Force-close stale connection and reconnect, retrying with backoff.

        The JellyFish controller only accepts one WebSocket connection at a
        time. If the previous connection's TCP socket is still ESTABLISHED at
        the kernel level (stale), new connection attempts will time out
        indefinitely. We must tear down the old connection first.

        Retries stay inside this loop (with _reconnecting set) so the
        on_error/on_close callbacks fired by each failed attempt don't
        schedule overlapping reconnects.
        """
        try:
            while not self._closing:
                LOGGER.debug(
                    "Force-closing stale connection to JellyFish controller at %s",
                    self.address,
                )
                await self._hass.async_add_executor_job(self._force_close_connection)
                # Give the controller time to release the old session
                await asyncio.sleep(2)
                failures = self._failed_reconnects
                try:
                    await self.async_connect()
                except HomeAssistantError:
                    self._failed_reconnects += 1
                    delay = min(
                        5 * 2 ** (self._failed_reconnects - 1), MAX_RECONNECT_DELAY
                    )
                    # Only the first failure is a warning; an outage shouldn't flood the log
                    first = self._failed_reconnects == 1
                    log = LOGGER.warning if first else LOGGER.debug
                    log(
                        "Reconnect to JellyFish controller at %s failed (attempt %s), "
                        "retrying in %ss",
                        self.address,
                        self._failed_reconnects,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                if failures:
                    LOGGER.warning(
                        "Reconnected to JellyFish controller at %s after %s failed attempts",
                        self.address,
                        failures,
                    )
                break
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
        # A half-open socket never fires on_close, so the library still reports
        # itself as connected. Clear the flag so async_connect() doesn't treat
        # the dead connection as live and skip reconnecting.
        try:
            self._controller._JellyFishController__ws_monitor._WebSocketMonitor__connected.clear()
        except Exception:  # noqa: BLE001
            pass

    def _note_missed_poll(self) -> None:
        """Forces a reconnect after repeated unanswered polls.

        If the controller stops responding without closing the socket (e.g. a
        half-open TCP connection), neither on_close nor on_error fires and the
        library keeps reporting itself as connected, so requests silently time
        out until the controller is restarted.
        """
        self._missed_polls += 1
        if (
            self._missed_polls < MAX_MISSED_POLLS
            or self._reconnecting
            or self.connecting
        ):
            return
        LOGGER.warning(
            "JellyFish controller at %s stopped responding; forcing reconnect",
            self.address,
        )
        self._missed_polls = 0
        self._reconnecting = True
        self._hass.async_create_task(self._async_reconnect())

    def _update_device_info(self) -> None:
        """Updates the device registry when controller info changes (e.g. after a firmware update)"""
        if not self.hostname:
            return
        registry = device_registry.async_get(self._hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.hostname)})
        if device and device.sw_version != self.version:
            registry.async_update_device(device.id, sw_version=self.version)

    def _update_patterns(self) -> None:
        # The controller pushes zone states before its pattern list on connect,
        # so a pattern saved on the controller can be captured by mistake
        saved = [p for p in self._captured if p in self._controller_patterns]
        for pattern in saved:
            del self._captured[pattern]
        if saved:
            self._store.async_delay_save(lambda: self._captured, 5)
        self.patterns = sorted(set(self._controller_patterns) | set(self._captured))

    async def async_load_captured_patterns(self) -> None:
        """Loads patterns captured in earlier sessions"""
        self._captured = await self._store.async_load() or {}
        self._update_patterns()

    def _patterns_changed(self) -> None:
        """Saves captured patterns and refreshes the effect lists"""
        self._update_patterns()
        self._store.async_delay_save(lambda: self._captured, 5)
        coord = self._coord
        if coord is not None:
            coord.async_update_listeners()

    def _capture_pattern(self, message: str) -> None:
        """Remembers a pattern the JellyFish app ran that isn't saved on the controller.

        The app sends its cloud library patterns (e.g. "Halloween/Lightning
        Storm") as a full pattern definition alongside the name, and the
        controller pushes that back to every client. Storing it lets the
        pattern be offered as an effect and replayed later.

        Only patterns that are playing are captured. The controller also
        reports each zone's last pattern when it's off (on every connect), and
        capturing those would bring back patterns removed with
        async_forget_captured_pattern. Ad-hoc looks the app runs without a
        name (or under a "_" folder like "_JF-CUSTOM") are skipped.
        """
        try:
            msg = json.loads(message)
        except ValueError:
            return
        run = msg.get("runPattern") if msg.get("cmd") == "fromCtlr" else None
        if not isinstance(run, dict) or not run.get("state"):
            return
        file = run.get("file") or ""
        if "/" not in file or file.startswith("_"):
            return
        try:
            config = json.loads(run.get("data") or "")
        except ValueError:
            return
        if not isinstance(config, dict):
            return

        async def store():
            if file in self._controller_patterns:
                return
            # The latest definition wins so a pattern updated in the app's
            # library doesn't go stale, except for brightness: it's chosen per
            # run (HA replays at any brightness and the controller echoes that
            # back), so keep the brightness the pattern was first captured with
            old = self._captured.get(file)
            if old is not None:
                old_config = json.loads(old)
                old_run, new_run = old_config.get("runData"), config.get("runData")
                if (
                    isinstance(old_run, dict)
                    and isinstance(new_run, dict)
                    and "brightness" in old_run
                ):
                    new_run["brightness"] = old_run["brightness"]
                if config == old_config:
                    return
                LOGGER.info("Updated captured pattern '%s'", file)
            else:
                LOGGER.info("Captured pattern '%s' from the JellyFish app", file)
            self._captured[file] = json.dumps(config, separators=(",", ":"))
            self._patterns_changed()

        asyncio.run_coroutine_threadsafe(store(), self._hass.loop)

    def async_forget_captured_pattern(self, pattern: str) -> bool:
        """Removes a captured pattern. Returns False if it wasn't captured."""
        if pattern not in self._captured:
            return False
        LOGGER.info("Forgetting captured pattern '%s'", pattern)
        del self._captured[pattern]
        self._patterns_changed()
        return True

    def _recieve_push(self, data):
        """Updates state data when a push event is received from the controller"""

        async def update():
            # Any message proves the connection is alive
            self._missed_polls = 0
            if NAME_DATA in data:
                self.name = self._controller.name
                LOGGER.debug("[PUSH UPDATE] Name: %s", self.name)
            elif HOSTNAME_DATA in data:
                self.hostname = self._controller.hostname
                LOGGER.debug("[PUSH UPDATE] Hostname: %s", self.hostname)
            elif FIRMWARE_VERSION_DATA in data:
                self.version = self._controller.firmware_version.ver
                LOGGER.debug("[PUSH UPDATE] Version: %s", self.version)
                self._update_device_info()
            elif ZONE_CONFIG_DATA in data:
                self.zones = self._controller.zone_names
                LOGGER.debug("[PUSH UPDATE] Zones: %s", ", ".join(self.zones))
            elif PATTERN_LIST_DATA in data or PATTERN_CONFIG_DATA in data:
                self._controller_patterns = self._controller.pattern_names
                self._update_patterns()
                LOGGER.debug(
                    "[PUSH UPDATE] Patterns: %s", ", ".join(self._controller_patterns)
                )
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
                # The controller may have rebooted (e.g. a firmware update), so
                # re-fetch its info and pattern list on the next poll
                self._refresh_static = True
                self._failed_reconnects = 0
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
        still missing or after a (re)connect, treat timeouts as non-fatal, and
        let push keep them current.
        """
        if self._reconnecting:
            # The reconnect loop owns the connection until it succeeds. Only
            # fail the poll once reconnecting has failed repeatedly, so a
            # routine idle-close doesn't log an error.
            if self._failed_reconnects < MAX_FAILED_RECONNECTS:
                return
            raise HomeAssistantError(
                f"Unable to reconnect to JellyFish Lighting controller at {self.address}"
            )
        await self.async_connect()
        refresh_static = self._refresh_static
        self._refresh_static = False
        try:
            LOGGER.debug("Getting refreshed data from JellyFish Lighting controller")
            if not self.name or refresh_static:
                try:
                    await self.async_get_controller_info()
                except HomeAssistantError:
                    LOGGER.debug(
                        "Could not fetch controller info from %s; "
                        "will retry on next poll or via push update",
                        self.address,
                    )
            if not self._controller_patterns or refresh_static:
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
            self._missed_polls = 0
        except HomeAssistantError:
            LOGGER.debug(
                "Zone state poll timed out for %s; state is current via push updates",
                self.address,
            )
            self._note_missed_poll()

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

    async def async_apply_pattern(
        self, pattern: str, zone: str, brightness: int = None
    ):
        """Turn one or more zones on and apply a preset pattern. Affects all zones if zone list is None.
        If brightness (0-100) is given, the pattern is applied at that brightness instead of the
        value it was saved with."""
        await self.async_connect()
        try:
            if pattern not in self._controller_patterns and pattern in self._captured:
                LOGGER.debug("Applying captured pattern '%s' to zone %s", pattern, zone)
                config = json.loads(self._captured[pattern])
                if brightness is not None and "runData" in config:
                    config["runData"]["brightness"] = brightness
                await self._hass.async_add_executor_job(
                    self._apply_pattern_config, pattern, config, zone
                )
            elif brightness is None:
                LOGGER.debug("Applying pattern '%s' to zone %s", pattern, zone)
                await self._hass.async_add_executor_job(
                    self._controller.apply_pattern, pattern, [zone], False
                )
            else:
                LOGGER.debug(
                    "Applying pattern '%s' to zone %s at %s%% brightness",
                    pattern,
                    zone,
                    brightness,
                )
                config = await self._hass.async_add_executor_job(
                    self._controller.get_pattern_config, pattern
                )
                config.runData.brightness = brightness
                await self._hass.async_add_executor_job(
                    self._apply_pattern_config, pattern, config, zone
                )
        except JellyFishException as ex:
            raise HomeAssistantError(
                f"Failed to apply pattern '{pattern}' on JellyFish Lighting zone '{zone}'"
            ) from ex

    def _apply_pattern_config(self, pattern: str, config, zone: str):
        """Run a pattern config while still reporting which pattern is active.

        The library's apply_pattern_config() sends `data` without `file`, so the
        controller reports an empty file and the zone's effect appears unset.
        Sending both keeps the effect attribute populated.
        """
        self._controller._JellyFishController__send(
            SetZoneStateRequest(state=1, zoneName=[zone], file=pattern, data=config)
        )

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
