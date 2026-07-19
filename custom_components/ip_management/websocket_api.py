"""Websocket API commands consumed by the IP Management frontend panel."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    SOURCE_ACTIVE_SCAN,
    SOURCE_PASSIVE_SCAN,
    WS_DEVICES_LIST,
    WS_DEVICES_SET_OVERRIDE,
    WS_SUBNETS_DELETE,
    WS_SUBNETS_LIST,
    WS_SUBNETS_SAVE,
)
from .storage import SubnetStore
from .device_matcher import DeviceMatcher
from .subnet_utils import InvalidCidrError, display_range


def _entry_data(hass: HomeAssistant) -> dict[str, Any]:
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        raise LookupError("IP Management is not set up")
    return next(iter(domain_data.values()))


def _store(hass: HomeAssistant) -> SubnetStore:
    return _entry_data(hass)["store"]


def _matcher(hass: HomeAssistant) -> DeviceMatcher:
    return _entry_data(hass)["matcher"]


@websocket_api.websocket_command({vol.Required("type"): WS_SUBNETS_LIST})
@websocket_api.async_response
async def ws_list_subnets(hass, connection, msg):
    subnets = []
    for record in _store(hass).subnets:
        record = dict(record)
        record["display_range"] = display_range(record["cidr"])
        subnets.append(record)
    connection.send_result(msg["id"], {"subnets": subnets})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SUBNETS_SAVE,
        # Named "subnet_id", not "id" — every websocket message already has a
        # reserved, auto-assigned numeric "id" field used for request/response
        # correlation, and reusing it here gets silently clobbered by that.
        vol.Optional("subnet_id"): str,
        vol.Required("cidr"): str,
        vol.Optional("label", default=""): str,
        vol.Optional("item_type", default=""): str,
        vol.Optional("notes"): vol.Any(str, None),
        vol.Optional("active_scan_enabled", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_save_subnet(hass, connection, msg):
    # Parent/child nesting is inferred from CIDR containment (see
    # SubnetStore._recompute_hierarchy) — there is no parent_id input here.
    payload = {k: v for k, v in msg.items() if k not in ("type", "id")}
    if "subnet_id" in payload:
        payload["id"] = payload.pop("subnet_id")
    try:
        record = await _store(hass).async_save_subnet(payload)
    except InvalidCidrError as err:
        connection.send_error(msg["id"], "invalid_subnet", str(err))
        return
    record = dict(record)
    record["display_range"] = display_range(record["cidr"])
    connection.send_result(msg["id"], {"subnet": record})


@websocket_api.websocket_command(
    {vol.Required("type"): WS_SUBNETS_DELETE, vol.Required("subnet_id"): str}
)
@websocket_api.async_response
async def ws_delete_subnet(hass, connection, msg):
    await _store(hass).async_delete_subnet(msg["subnet_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): WS_DEVICES_LIST})
@websocket_api.async_response
async def ws_list_devices(hass, connection, msg):
    entry_data = _entry_data(hass)
    store: SubnetStore = entry_data["store"]
    matcher: DeviceMatcher = entry_data["matcher"]

    # device_tracker/config_entry are the authoritative sources; active/passive
    # scan results only fill in devices neither of those already resolved
    # (setdefault below never overwrites an existing entry).
    device_ips = matcher.async_get_device_ips()

    coordinator = entry_data.get("active_scan_coordinator")
    if coordinator is not None and coordinator.data:
        for host in coordinator.data:
            info = matcher.resolve_scan_result(host, source=SOURCE_ACTIVE_SCAN)
            device_ips.setdefault(info.device_id, info)

    passive_scanner = entry_data.get("passive_scanner")
    if passive_scanner is not None:
        for host in passive_scanner.snapshot():
            info = matcher.resolve_scan_result(host, source=SOURCE_PASSIVE_SCAN)
            device_ips.setdefault(info.device_id, info)

    matches = matcher.async_match_devices_to_subnets(
        store.subnets, store.device_overrides, device_ips=device_ips
    )
    connection.send_result(msg["id"], {"devices": matches})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_DEVICES_SET_OVERRIDE,
        vol.Required("device_id"): str,
        vol.Optional("subnet_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_set_device_override(hass, connection, msg):
    await _store(hass).async_set_device_override(
        msg["device_id"], msg.get("subnet_id")
    )
    connection.send_result(msg["id"], {})


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list_subnets)
    websocket_api.async_register_command(hass, ws_save_subnet)
    websocket_api.async_register_command(hass, ws_delete_subnet)
    websocket_api.async_register_command(hass, ws_list_devices)
    websocket_api.async_register_command(hass, ws_set_device_override)
