"""Adds config flow for Blueprint."""
from typing import Any
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol
from jellyfishlightspy import JellyFishException
from .api import JellyfishLightingApiClient
from .const import (
    LOGGER,
    DOMAIN,
    CONF_ADDRESS,
    CONF_NAME,
    CONF_HOSTNAME,
    CONF_VERSION,
)


class JellyfishLightingFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for JellyFish Lighting"""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            try:
                host = user_input[CONF_ADDRESS]
                LOGGER.info(
                    "Testing connection to JellyFish Lighting controller at %s...", host
                )
                session = async_create_clientsession(self.hass)
                client = JellyfishLightingApiClient(host, session, self.hass)
                await client.async_connect()
                LOGGER.info(
                    "Successfully connected to JellyFish Lighting controller at %s!",
                    host,
                )
                await client.async_get_controller_info()
                data = user_input.copy()
                data[CONF_NAME] = client.name
                data[CONF_HOSTNAME] = client.hostname
                data[CONF_VERSION] = client.version
                await client.async_disconnect()
                return self.async_create_entry(
                    title=user_input[CONF_ADDRESS], data=data
                )
            except JellyFishException:
                LOGGER.exception(
                    "Failed to connect to JellyFish Lighting controller at %s", host
                )
                errors["base"] = "cannot_connect"
        else:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors or {},
        )
