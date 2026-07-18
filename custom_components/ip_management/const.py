"""Constants for the IP Management integration."""
from __future__ import annotations

DOMAIN = "ip_management"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.subnets"

PANEL_URL = "ip-management"
PANEL_TITLE = "IP Management"
PANEL_ICON = "mdi:lan"
PANEL_COMPONENT_NAME = "ip-management-panel"
STATIC_URL_PATH = "/ip_management_static"
STATIC_JS_FILE = "ip-management-panel.js"
# Bump whenever www/ip-management-panel.js changes. Static assets are served
# with aggressive cache headers, so without a version query string browsers
# would keep serving a stale (possibly incompatible) copy of the panel after
# an update until the user manually clears their cache.
PANEL_JS_VERSION = "2"

WS_SUBNETS_LIST = f"{DOMAIN}/subnets/list"
WS_SUBNETS_SAVE = f"{DOMAIN}/subnets/save"
WS_SUBNETS_DELETE = f"{DOMAIN}/subnets/delete"
WS_DEVICES_LIST = f"{DOMAIN}/devices/list"
WS_DEVICES_SET_OVERRIDE = f"{DOMAIN}/devices/set_override"
