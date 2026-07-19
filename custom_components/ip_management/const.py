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
PANEL_JS_VERSION = "5"

WS_SUBNETS_LIST = f"{DOMAIN}/subnets/list"
WS_SUBNETS_SAVE = f"{DOMAIN}/subnets/save"
WS_SUBNETS_DELETE = f"{DOMAIN}/subnets/delete"
WS_DEVICES_LIST = f"{DOMAIN}/devices/list"
WS_DEVICES_SET_OVERRIDE = f"{DOMAIN}/devices/set_override"

# Options-flow keys (Settings -> Devices & Services -> IP Management -> Configure).
CONF_ENABLE_ACTIVE_SCAN = "enable_active_scan"
CONF_ACTIVE_SCAN_INTERVAL_HOURS = "active_scan_interval_hours"
CONF_ENABLE_PASSIVE_DISCOVERY = "enable_passive_discovery"

DEFAULT_ENABLE_ACTIVE_SCAN = False
DEFAULT_ACTIVE_SCAN_INTERVAL_HOURS = 24
DEFAULT_ENABLE_PASSIVE_DISCOVERY = False

# Active scanning pings every host address in each registered subnet. Cap the
# per-subnet host count so an accidentally huge subnet (e.g. a /8) can't turn
# into an unbounded flood of the local network; larger subnets are skipped
# with a log warning rather than scanned partially or silently ignored.
MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET = 512

# Device-IP sources, surfaced in the UI so users can see how each entry was found.
SOURCE_DEVICE_TRACKER = "device_tracker"
SOURCE_CONFIG_ENTRY = "config_entry"
SOURCE_ACTIVE_SCAN = "active_scan"
SOURCE_PASSIVE_SCAN = "passive_scan"

# Curated list of mDNS service types commonly advertised by home/IoT devices.
# Passive discovery only sees what's advertised under one of these — it is
# not a full dynamic service-type enumeration (see PLAN.md).
ZEROCONF_SERVICE_TYPES = [
    "_http._tcp.local.",
    "_hap._tcp.local.",  # HomeKit
    "_googlecast._tcp.local.",  # Chromecast
    "_airplay._tcp.local.",
    "_raop._tcp.local.",  # AirPlay audio
    "_ipp._tcp.local.",  # network printers
    "_printer._tcp.local.",
    "_spotify-connect._tcp.local.",
    "_workstation._tcp.local.",
]
