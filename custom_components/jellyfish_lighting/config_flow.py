"""Adds config flow for Blueprint."""
from typing import Any
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol
from .api import JellyfishLightingApiClient
from .const import (
    LOGGER,
    CONF_HOST,
    DOMAIN,
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

        # Only a single instance of the integration is allowed
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            valid = await self._test_connection(user_input[CONF_HOST])
            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )
            else:
                errors["base"] = "cannot_connect"
        else:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors or {},
        )

    async def _test_connection(self, host):
        """Return true if host is valid."""
        try:
            LOGGER.info(
                "Testing connection to JellyFish Lighting controller at %s...", host
            )
            session = async_create_clientsession(self.hass)
            client = JellyfishLightingApiClient(host, session, self.hass)
            await client.async_connect()
            LOGGER.info(
                "Successfully connected to JellyFish Lighting controller at %s!", host
            )
            return True
        except Exception:  # pylint: disable=broad-except
            return False
