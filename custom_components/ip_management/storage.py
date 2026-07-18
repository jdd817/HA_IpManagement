"""Persistent storage for subnet records and manual device overrides."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .subnet_utils import infer_parent_ids, parse_network


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubnetStore:
    """Wraps Home Assistant's Store helper with subnet-specific CRUD.

    Parent/child nesting is always inferred from CIDR containment — there is
    no user-settable parent field. Every save or delete recomputes the full
    hierarchy (`infer_parent_ids`), so inserting a subnet "between" two
    existing ones automatically re-parents the more specific one, and
    deleting a subnet automatically re-parents its former children to its
    own parent.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._subnets: dict[str, dict[str, Any]] = {}
        self._device_overrides: dict[str, str] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self._subnets = {s["id"]: s for s in data.get("subnets", [])}
            self._device_overrides = dict(data.get("device_overrides", {}))
            self._recompute_hierarchy()

    async def _async_persist(self) -> None:
        await self._store.async_save(
            {
                "subnets": list(self._subnets.values()),
                "device_overrides": self._device_overrides,
            }
        )

    @property
    def subnets(self) -> list[dict[str, Any]]:
        return list(self._subnets.values())

    @property
    def device_overrides(self) -> dict[str, str]:
        return dict(self._device_overrides)

    def _recompute_hierarchy(self) -> None:
        cidrs_by_id = {sid: s["cidr"] for sid, s in self._subnets.items()}
        for subnet_id, parent_id in infer_parent_ids(cidrs_by_id).items():
            self._subnets[subnet_id]["parent_id"] = parent_id

    async def async_save_subnet(self, subnet: dict[str, Any]) -> dict[str, Any]:
        """Create or update a subnet. Raises InvalidCidrError on a bad CIDR."""
        subnet_id = subnet.get("id") or str(uuid.uuid4())

        parse_network(subnet["cidr"])  # validates; raises InvalidCidrError

        existing = self._subnets.get(subnet_id, {})
        record = {
            **existing,
            "id": subnet_id,
            "cidr": subnet["cidr"],
            "label": subnet.get("label", existing.get("label", "")),
            "item_type": subnet.get("item_type", existing.get("item_type", "")),
            "notes": subnet.get("notes", existing.get("notes")),
            "updated_at": _utcnow_iso(),
        }
        record.setdefault("created_at", _utcnow_iso())

        self._subnets[subnet_id] = record
        self._recompute_hierarchy()
        await self._async_persist()
        return record

    async def async_delete_subnet(self, subnet_id: str) -> None:
        if subnet_id not in self._subnets:
            return

        del self._subnets[subnet_id]
        self._recompute_hierarchy()
        await self._async_persist()

    async def async_set_device_override(
        self, device_id: str, subnet_id: str | None
    ) -> None:
        if subnet_id is None:
            self._device_overrides.pop(device_id, None)
        else:
            self._device_overrides[device_id] = subnet_id
        await self._async_persist()
