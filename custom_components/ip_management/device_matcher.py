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
    source: str  # "device_tracker" | "config_entry"


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

    def async_match_devices_to_subnets(
        self,
        subnets: list[dict[str, Any]],
        device_overrides: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Return per-device match info: device + resolved subnet_id (or None)."""
        cidr_by_subnet_id = {s["id"]: s["cidr"] for s in subnets}
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
