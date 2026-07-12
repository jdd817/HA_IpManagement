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

WS_SUBNETS_LIST = f"{DOMAIN}/subnets/list"
WS_SUBNETS_SAVE = f"{DOMAIN}/subnets/save"
WS_SUBNETS_DELETE = f"{DOMAIN}/subnets/delete"
WS_DEVICES_LIST = f"{DOMAIN}/devices/list"
WS_DEVICES_SET_OVERRIDE = f"{DOMAIN}/devices/set_override"
