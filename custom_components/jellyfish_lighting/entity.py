"""JellyfishLightingEntity class"""

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, ATTRIBUTION, CONF_HOSTNAME


class JellyfishLightingEntity(CoordinatorEntity):
    """Entity for the JellyFish Lighting integration"""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    # @property
    # def should_poll(self) -> bool:
    #     return False

    @property
    def device_info(self) -> DeviceInfo:
        # Only link to the device created in async_setup_entry. Passing name or
        # sw_version here overwrote the device with the values saved in the
        # config entry at setup, so a firmware update never showed up. Fall back
        # to the saved hostname if the controller hasn't reported it yet.
        hostname = self.coordinator.api.hostname or self.config_entry.data.get(
            CONF_HOSTNAME
        )
        return DeviceInfo(identifiers={(DOMAIN, hostname)})

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            # "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }
