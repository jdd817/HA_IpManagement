"""Passive discovery: listens for mDNS/Bonjour announcements via Home
Assistant's shared zeroconf instance, for a curated list of common
home/IoT service types (see const.ZEROCONF_SERVICE_TYPES).

Unlike active_scanner.py this never sends any probing traffic of its own —
it only listens for what devices already broadcast — so it isn't scoped to
registered subnets and has no host-count cap. It also only sees whatever
happens to advertise under one of the curated service types; it's not a
full dynamic mDNS service-type enumeration (see PLAN.md).
"""
from __future__ import annotations

import logging

from homeassistant.components import zeroconf as ha_zeroconf
from homeassistant.core import HomeAssistant
from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .const import ZEROCONF_SERVICE_TYPES
from .device_matcher import DiscoveredHost

_LOGGER = logging.getLogger(__name__)

SERVICE_INFO_TIMEOUT_MS = 3000


def friendly_name_from_service_info(info: AsyncServiceInfo, service_name: str) -> str:
    """Best-effort human-readable name for a discovered mDNS service."""
    server = (info.server or "").rstrip(".")
    return server or service_name.split(".", 1)[0]


class PassiveScanner:
    """Wraps an AsyncServiceBrowser over HA's shared zeroconf instance."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._browser: AsyncServiceBrowser | None = None
        self._hosts: dict[str, DiscoveredHost] = {}

    async def async_start(self) -> None:
        if self._browser is not None:
            return
        haz = await ha_zeroconf.async_get_async_instance(self._hass)
        self._browser = AsyncServiceBrowser(
            haz.zeroconf,
            ZEROCONF_SERVICE_TYPES,
            handlers=[self._on_service_state_change],
        )

    async def async_stop(self) -> None:
        if self._browser is not None:
            await self._browser.async_cancel()
            self._browser = None

    def snapshot(self) -> list[DiscoveredHost]:
        return list(self._hosts.values())

    def _on_service_state_change(
        self, zeroconf_obj, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        """Fired by AsyncServiceBrowser on the event loop — safe to schedule a task from."""
        if state_change == ServiceStateChange.Removed:
            return
        self._hass.async_create_task(
            self._async_resolve(service_type, name),
            name=f"ip_management_mdns_resolve_{name}",
        )

    async def _async_resolve(self, service_type: str, name: str) -> None:
        haz = await ha_zeroconf.async_get_async_instance(self._hass)
        info = await haz.async_get_service_info(
            service_type, name, timeout=SERVICE_INFO_TIMEOUT_MS
        )
        if info is None:
            return

        friendly_name = friendly_name_from_service_info(info, name)
        for ip in info.parsed_addresses(version=IPVersion.V4Only):
            self._hosts[ip] = DiscoveredHost(ip=ip, mac=None, name=friendly_name)
