"""Tests for the discovery options flow (Settings -> ... -> Configure)."""
import asyncio
from types import SimpleNamespace

from custom_components.ip_management.config_flow import IPManagementOptionsFlow
from custom_components.ip_management.const import (
    CONF_ACTIVE_SCAN_INTERVAL_HOURS,
    CONF_ENABLE_ACTIVE_SCAN,
    CONF_ENABLE_PASSIVE_DISCOVERY,
    DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS,
    DEFAULT_ENABLE_ACTIVE_SCAN,
    DEFAULT_ENABLE_PASSIVE_DISCOVERY,
)


def run(coro):
    return asyncio.run(coro)


def make_flow(options=None):
    flow = IPManagementOptionsFlow()
    # `config_entry` is normally wired up by HA's flow manager; set the
    # compatibility-shim private attribute directly rather than going
    # through the (deprecated-for-custom-integrations) public setter.
    flow._config_entry = SimpleNamespace(options=options or {})
    return flow


def test_shows_form_with_defaults_when_no_options_set():
    flow = make_flow(options={})

    result = run(flow.async_step_init())

    assert result["type"] == "form"
    schema_defaults = {
        str(key): key.default() for key in result["data_schema"].schema
    }
    assert schema_defaults[CONF_ENABLE_ACTIVE_SCAN] == DEFAULT_ENABLE_ACTIVE_SCAN
    assert (
        schema_defaults[CONF_ACTIVE_SCAN_INTERVAL_HOURS]
        == DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS
    )
    assert (
        schema_defaults[CONF_ENABLE_PASSIVE_DISCOVERY]
        == DEFAULT_ENABLE_PASSIVE_DISCOVERY
    )


def test_shows_form_with_previously_saved_options():
    flow = make_flow(
        options={
            CONF_ENABLE_ACTIVE_SCAN: True,
            CONF_ACTIVE_SCAN_INTERVAL_HOURS: 6,
            CONF_ENABLE_PASSIVE_DISCOVERY: True,
        }
    )

    result = run(flow.async_step_init())

    schema_defaults = {
        str(key): key.default() for key in result["data_schema"].schema
    }
    assert schema_defaults[CONF_ENABLE_ACTIVE_SCAN] is True
    assert schema_defaults[CONF_ACTIVE_SCAN_INTERVAL_HOURS] == 6
    assert schema_defaults[CONF_ENABLE_PASSIVE_DISCOVERY] is True


def test_submitting_creates_entry_with_provided_data():
    flow = make_flow()
    user_input = {
        CONF_ENABLE_ACTIVE_SCAN: True,
        CONF_ACTIVE_SCAN_INTERVAL_HOURS: 12,
        CONF_ENABLE_PASSIVE_DISCOVERY: False,
    }

    result = run(flow.async_step_init(user_input))

    assert result["type"] == "create_entry"
    assert result["data"] == user_input
