"""Config flow for IP Management.

The integration takes no user input — the flow only exists so it can be
added once from Settings -> Devices & Services. All real configuration
(subnets, nesting, labels) happens in the custom sidebar panel.
"""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class IPManagementConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for IP Management."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="IP Management", data={})

        return self.async_show_form(step_id="user")
