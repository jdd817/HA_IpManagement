"""DataUpdateCoordinator for the active (ping-sweep) scanner.

Schedules ActiveScanner.async_scan on a configurable interval and caches the
result (`coordinator.data`) so websocket_api can read the latest scan
without triggering a live network scan per request.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .active_scanner import ActiveScanner
from .const import DOMAIN
from .device_matcher import DiscoveredHost
from .storage import SubnetStore

_LOGGER = logging.getLogger(__name__)


class ActiveScanCoordinator(DataUpdateCoordinator[list[DiscoveredHost]]):
    """Periodically ping-sweeps registered subnets (see active_scanner.py)."""

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
        return await self._scanner.async_scan(self._store.subnets)
