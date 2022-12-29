"""Constants for jellyfish-lighting."""
# Base component constants
NAME = "Jellyfish Lighting"
DEVICE = "Jellyfish Controller"
DOMAIN = "jellyfish_lighting"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.0.0"
ATTRIBUTION = "Leverages the Jellyfish Lighting Python API \
    created by @vinenoobjelly https://github.com/vinenoobjelly/jellyfishlights-py"
ISSUE_URL = "https://github.com/bdunn44/hass-jellyfish-lighting/issues"

# Icons
ICON = "mdi:home-lightbulb-outline"

# Platforms
LIGHT = "light"

# Configuration and options
CONF_HOST = "host"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
