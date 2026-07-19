"""DataUpdateCoordinator for the active (ping-sweep) scanner.

Schedules ActiveScanner.async_scan on a configurable interval and caches the
result (`coordinator.data`) so websocket_api can read the latest scan
without triggering a live network scan per request.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .active_scanner import ActiveScanner
from .const import DOMAIN
from .device_matcher import DiscoveredHost
from .storage import SubnetStore

_LOGGER = logging.getLogger(__name__)


def scannable_subnets(subnets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Subnets opted in to active scanning via their own `active_scan_enabled` flag.

    Enabling active scanning globally (the options-flow toggle) only turns
    the coordinator on — it never implies scanning every registered subnet.
    Each subnet needs its own opt-in (set from the Subnet Management form),
    so a user can restrict scanning to just the areas that need it.
    """
    return [s for s in subnets if s.get("active_scan_enabled")]


class ActiveScanCoordinator(DataUpdateCoordinator[list[DiscoveredHost]]):
    """Periodically ping-sweeps subnets opted in to active scanning."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        store: SubnetStore,
        scanner: ActiveScanner,
        interval_hours: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_active_scan",
            update_interval=timedelta(hours=interval_hours),
        )
        self._store = store
        self._scanner = scanner

    async def _async_update_data(self) -> list[DiscoveredHost]:
        return await self._scanner.async_scan(scannable_subnets(self._store.subnets))
