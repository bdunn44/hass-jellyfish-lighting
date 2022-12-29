"""JellyfishLightingEntity class"""
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, ATTRIBUTION


class JellyfishLightingEntity(CoordinatorEntity):
    """Entity for the JellyFish Lighting integration"""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return self.config_entry.entry_id

    @property
    def device_info(self):
        return {"identifiers": {(DOMAIN, self.config_entry.data.get(CONF_HOST))}}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            # "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }
