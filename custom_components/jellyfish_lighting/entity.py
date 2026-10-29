"""JellyfishLightingEntity class"""

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, ATTRIBUTION


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
        # config entry at setup, so a firmware update never showed up.
        return DeviceInfo(identifiers={(DOMAIN, self.coordinator.api.hostname)})

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            # "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }
