"""JellyfishLightingEntity class"""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    NAME,
    DEVICE,
    ATTRIBUTION,
    CONF_NAME,
    CONF_HOSTNAME,
    CONF_VERSION,
)


class JellyfishLightingEntity(CoordinatorEntity):
    """Entity for the JellyFish Lighting integration"""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def device_info(self) -> DeviceInfo:
        data = self.config_entry.data
        return DeviceInfo(
            identifiers={
                (DOMAIN, data.get(CONF_HOSTNAME)),
            },
            name=data.get(CONF_NAME),
            manufacturer=NAME,
            model=DEVICE,
            sw_version=data.get(CONF_VERSION),
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            # "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }
