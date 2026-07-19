"""Resolves Home Assistant devices to IP addresses and matches them to subnets.

Home Assistant has no single canonical "device IP" field, so candidates are
gathered from a few different places and merged, with `device_tracker`
attributes taking priority (most likely to be current) over config-entry
data (often the address used at setup time, which may go stale).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .subnet_utils import most_specific_match

_IP_ATTRIBUTES = ("ip_address", "ip")
_IP_DATA_KEYS = ("host", "ip_address", "ip")


@dataclass(frozen=True)
class DeviceIpInfo:
    device_id: str
    name: str
    ip_address: str
    source: str  # "device_tracker" | "config_entry" | "active_scan" | "passive_scan"


@dataclass(frozen=True)
class DiscoveredHost:
    """A host found by active (ping) or passive (mDNS) discovery.

    Produced by active_scanner.py / passive_scanner.py and resolved to a
    DeviceIpInfo via DeviceMatcher.resolve_scan_result — kept independent of
    both so neither scanner needs to know about device registry lookups.
    """

    ip: str
    mac: str | None = None
    name: str | None = None


def _looks_like_ipv4(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


class DeviceMatcher:
    """Gathers device -> IP candidates from HA and matches them to subnets."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def _from_device_tracker(self) -> dict[str, DeviceIpInfo]:
        hass = self._hass
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        results: dict[str, DeviceIpInfo] = {}

        for state in hass.states.async_all("device_tracker"):
            ip_address = next(
                (
                    state.attributes.get(attr)
                    for attr in _IP_ATTRIBUTES
                    if _looks_like_ipv4(state.attributes.get(attr))
                ),
                None,
            )
            if ip_address is None:
                continue

            entity_entry = ent_reg.async_get(state.entity_id)
            device_id = entity_entry.device_id if entity_entry else None
            if device_id is None:
                continue

            device_entry = dev_reg.async_get(device_id)
            name = state.name
            if device_entry is not None:
                name = device_entry.name_by_user or device_entry.name or name

            results[device_id] = DeviceIpInfo(
                device_id=device_id,
                name=name,
                ip_address=ip_address,
                source="device_tracker",
            )
        return results

    def _from_config_entries(self) -> dict[str, DeviceIpInfo]:
        hass = self._hass
        dev_reg = dr.async_get(hass)
        results: dict[str, DeviceIpInfo] = {}

        for entry in hass.config_entries.async_entries():
            ip_address = next(
                (
                    entry.data.get(key)
                    for key in _IP_DATA_KEYS
                    if _looks_like_ipv4(entry.data.get(key))
                ),
                None,
            )
            if ip_address is None:
                continue

            for device_entry in dr.async_entries_for_config_entry(
                dev_reg, entry.entry_id
            ):
                name = device_entry.name_by_user or device_entry.name or device_entry.id
                results[device_entry.id] = DeviceIpInfo(
                    device_id=device_entry.id,
                    name=name,
                    ip_address=ip_address,
                    source="config_entry",
                )
        return results

    def async_get_device_ips(self) -> dict[str, DeviceIpInfo]:
        """Merge candidate sources; device_tracker wins over config-entry data."""
        merged = self._from_config_entries()
        merged.update(self._from_device_tracker())
        return merged

    def resolve_scan_result(self, host: DiscoveredHost, source: str) -> DeviceIpInfo:
        """Turn a scanner's raw find into a DeviceIpInfo.

        If the host's MAC matches a connection already in the device
        registry, it's attributed to that real device (so it merges with,
        rather than duplicates, anything device_tracker/config_entry already
        found for it). Otherwise it gets a synthetic `scan:<ip>` id so it can
        still be shown as a newly-discovered, unregistered device.
        """
        device_entry = None
        if host.mac:
            dev_reg = dr.async_get(self._hass)
            device_entry = dev_reg.async_get_device(
                connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(host.mac))}
            )

        if device_entry is not None:
            device_id = device_entry.id
            name = device_entry.name_by_user or device_entry.name or host.ip
        else:
            device_id = f"scan:{host.ip}"
            name = host.name or host.ip

        return DeviceIpInfo(
            device_id=device_id, name=name, ip_address=host.ip, source=source
        )

    def async_match_devices_to_subnets(
        self,
        subnets: list[dict[str, Any]],
        device_overrides: dict[str, str],
        device_ips: dict[str, DeviceIpInfo] | None = None,
    ) -> list[dict[str, Any]]:
        """Return per-device match info: device + resolved subnet_id (or None).

        `device_ips` lets callers supply a pre-merged set (e.g. websocket_api
        folding in active/passive scan results via resolve_scan_result)
        instead of just what async_get_device_ips finds on its own.
        """
        cidr_by_subnet_id = {s["id"]: s["cidr"] for s in subnets}
        if device_ips is None:
            device_ips = self.async_get_device_ips()

        matches: list[dict[str, Any]] = []
        for device_id, info in device_ips.items():
            if device_id in device_overrides:
                subnet_id = device_overrides[device_id]
            else:
                best_cidr = most_specific_match(
                    info.ip_address, cidr_by_subnet_id.values()
                )
                subnet_id = next(
                    (
                        sid
                        for sid, cidr in cidr_by_subnet_id.items()
                        if cidr == best_cidr
                    ),
                    None,
                )

            matches.append(
                {
                    "device_id": device_id,
                    "name": info.name,
                    "ip_address": info.ip_address,
                    "subnet_id": subnet_id,
                    "source": info.source,
                }
            )
        return matches
