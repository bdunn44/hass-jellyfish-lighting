"""Constants for jellyfish-lighting."""
# Base component constants
NAME = "Jellyfish Lighting"
DOMAIN = "jellyfish_lighting"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.1"
ATTRIBUTION = "Data provided by http://jsonplaceholder.typicode.com/"
ISSUE_URL = "https://github.com/bdunn44/hass-jellyfish-lighting/issues"

# Icons
ICON = "mdi:home-lightbulb-outline"

# Device classes
BINARY_SENSOR_DEVICE_CLASS = "connectivity"

# Platforms
LIGHT = "light"
PLATFORMS = [LIGHT]

# Configuration and options
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_NAME = DOMAIN


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""