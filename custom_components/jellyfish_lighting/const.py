"""Constants for jellyfish-lighting integration."""
from datetime import timedelta
import logging

LOGGER = logging.getLogger(__package__)
SCAN_INTERVAL = timedelta(seconds=15)

# Base component constants
NAME = "JellyFish Lighting"
DEVICE = "Jellyfish Controller"
DOMAIN = "jellyfish_lighting"
DOMAIN_DATA = f"{DOMAIN}_data"
ATTRIBUTION = "Leverages the JellyFish Lighting Python API \
    created by @vinenoobjelly https://github.com/vinenoobjelly/jellyfishlights-py"
ISSUE_URL = "https://github.com/bdunn44/hass-jellyfish-lighting/issues"

# Icons
ICON = "mdi:home-lightbulb-outline"

# Platforms
LIGHT = "light"

# Configuration and options
CONF_HOST = "host"
DEFAULT_BRIGHTNESS = 100
DEFAULT_COLOR = (255, 193, 7)

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
