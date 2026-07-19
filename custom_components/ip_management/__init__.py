"""The IP Management integration.

Registers a sidebar panel for tracking user-defined subnets (with nesting)
and the Home Assistant devices whose IP address falls within them, plus two
optional discovery features (both off by default, toggled via the options
flow — Settings -> Devices & Services -> IP Management -> Configure):

- Active scan: ping-sweeps subnets registered in the panel on a configurable
  interval (active_scanner.py + coordinator.py).
- Passive discovery: listens for mDNS/Bonjour announcements
  (passive_scanner.py).

Both only ever *fill gaps* in device_matcher.py's device_tracker/config-entry
based matching (see websocket_api.ws_list_devices) — neither can override a
device HA already has better information for.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .active_scanner import ActiveScanner
from .const import (
    CONF_ACTIVE_SCAN_INTERVAL_HOURS,
    CONF_ENABLE_ACTIVE_SCAN,
    CONF_ENABLE_PASSIVE_DISCOVERY,
    DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS,
    DEFAULT_ENABLE_ACTIVE_SCAN,
    DEFAULT_ENABLE_PASSIVE_DISCOVERY,
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_JS_VERSION,
    PANEL_TITLE,
    PANEL_URL,
    STATIC_JS_FILE,
    STATIC_URL_PATH,
)
from .coordinator import ActiveScanCoordinator
from .device_matcher import DeviceMatcher
from .passive_scanner import PassiveScanner
from .storage import SubnetStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IP Management from a config entry."""
    store = SubnetStore(hass)
    await store.async_load()

    entry_data: dict = {
        "store": store,
        "matcher": DeviceMatcher(hass),
        "active_scan_coordinator": None,
        "passive_scanner": None,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry_data

    if entry.options.get(CONF_ENABLE_ACTIVE_SCAN, DEFAULT_ENABLE_ACTIVE_SCAN):
        interval_hours = entry.options.get(
            CONF_ACTIVE_SCAN_INTERVAL_HOURS, DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS
        )
        coordinator = ActiveScanCoordinator(
            hass, entry, store, ActiveScanner(hass), interval_hours
        )
        await coordinator.async_config_entry_first_refresh()
        entry_data["active_scan_coordinator"] = coordinator

    if entry.options.get(CONF_ENABLE_PASSIVE_DISCOVERY, DEFAULT_ENABLE_PASSIVE_DISCOVERY):
        passive_scanner = PassiveScanner(hass)
        await passive_scanner.async_start()
        entry_data["passive_scanner"] = passive_scanner

    async_register_websocket_commands(hass)
    await _async_register_static_path(hass)
    await _async_register_panel(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data is None:
        return True

    coordinator: ActiveScanCoordinator | None = entry_data.get("active_scan_coordinator")
    if coordinator is not None:
        await coordinator.async_shutdown()

    passive_scanner: PassiveScanner | None = entry_data.get("passive_scanner")
    if passive_scanner is not None:
        await passive_scanner.async_stop()

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. discovery toggles/interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


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
        # The `?v=` query string busts the browser cache set by
        # cache_headers=True above whenever PANEL_JS_VERSION is bumped, so
        # panel updates take effect without users needing to manually clear
        # their cache.
        module_url=f"{STATIC_URL_PATH}/{STATIC_JS_FILE}?v={PANEL_JS_VERSION}",
        embed_iframe=False,
        require_admin=True,
    )
    hass.data[DOMAIN]["_panel_registered"] = True
