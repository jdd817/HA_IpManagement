"""Config + options flow for IP Management.

The initial setup flow takes no user input — subnets, nesting, and labels
are all managed from the custom sidebar panel, not here. The *options*
flow (Settings -> Devices & Services -> IP Management -> Configure) is
where the two active/passive discovery features are toggled, since those
affect background network activity rather than data the panel edits.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ACTIVE_SCAN_INTERVAL_HOURS,
    CONF_ENABLE_ACTIVE_SCAN,
    CONF_ENABLE_PASSIVE_DISCOVERY,
    DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS,
    DEFAULT_ENABLE_ACTIVE_SCAN,
    DEFAULT_ENABLE_PASSIVE_DISCOVERY,
    DOMAIN,
)


class IPManagementConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for IP Management."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="IP Management", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IPManagementOptionsFlow:
        return IPManagementOptionsFlow()


class IPManagementOptionsFlow(config_entries.OptionsFlow):
    """Toggle active (ping-sweep) and passive (mDNS) discovery, and the
    active-scan polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_ACTIVE_SCAN,
                    default=options.get(
                        CONF_ENABLE_ACTIVE_SCAN, DEFAULT_ENABLE_ACTIVE_SCAN
                    ),
                ): bool,
                vol.Required(
                    CONF_ACTIVE_SCAN_INTERVAL_HOURS,
                    default=options.get(
                        CONF_ACTIVE_SCAN_INTERVAL_HOURS,
                        DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 30)),
                vol.Required(
                    CONF_ENABLE_PASSIVE_DISCOVERY,
                    default=options.get(
                        CONF_ENABLE_PASSIVE_DISCOVERY, DEFAULT_ENABLE_PASSIVE_DISCOVERY
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
