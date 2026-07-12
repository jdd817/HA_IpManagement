"""The IP Management integration.

Registers a sidebar panel for tracking user-defined subnets (with nesting)
and the Home Assistant devices whose IP address falls within them.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
    STATIC_JS_FILE,
    STATIC_URL_PATH,
)
from .device_matcher import DeviceMatcher
from .storage import SubnetStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IP Management from a config entry."""
    store = SubnetStore(hass)
    await store.async_load()

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = {
        "store": store,
        "matcher": DeviceMatcher(hass),
    }

    async_register_websocket_commands(hass)
    await _async_register_static_path(hass)
    await _async_register_panel(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def _async_register_static_path(hass: HomeAssistant) -> None:
    www_path = str(Path(__file__).parent / "www")

    try:
        # Home Assistant 2024.7+
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, www_path, True)]
        )
    except ImportError:
        # Older core versions
        hass.http.register_static_path(STATIC_URL_PATH, www_path, cache_headers=True)


async def _async_register_panel(hass: HomeAssistant) -> None:
    already_registered = hass.data.get(DOMAIN, {}).get("_panel_registered", False)
    if already_registered:
        return

    from homeassistant.components.panel_custom import async_register_panel

    await async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_COMPONENT_NAME,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL_PATH}/{STATIC_JS_FILE}",
        embed_iframe=False,
        require_admin=True,
    )
    hass.data[DOMAIN]["_panel_registered"] = True
