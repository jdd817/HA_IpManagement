"""Persistent storage for subnet records and manual device overrides."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .subnet_utils import SubnetNestingError, validate_nesting


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubnetStore:
    """Wraps Home Assistant's Store helper with subnet-specific CRUD + validation."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._subnets: dict[str, dict[str, Any]] = {}
        self._device_overrides: dict[str, str] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self._subnets = {s["id"]: s for s in data.get("subnets", [])}
            self._device_overrides = dict(data.get("device_overrides", {}))

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

    def _parent_cidr(self, parent_id: str | None) -> str | None:
        if parent_id is None:
            return None
        parent = self._subnets.get(parent_id)
        if parent is None:
            raise SubnetNestingError(f"Parent subnet '{parent_id}' does not exist")
        return parent["cidr"]

    async def async_save_subnet(self, subnet: dict[str, Any]) -> dict[str, Any]:
        """Create or update a subnet. Raises InvalidCidrError/SubnetNestingError."""
        subnet_id = subnet.get("id") or str(uuid.uuid4())
        parent_id = subnet.get("parent_id")

        if parent_id == subnet_id:
            raise SubnetNestingError("A subnet cannot be its own parent")

        validate_nesting(subnet["cidr"], self._parent_cidr(parent_id))

        existing = self._subnets.get(subnet_id, {})
        record = {
            **existing,
            "id": subnet_id,
            "cidr": subnet["cidr"],
            "parent_id": parent_id,
            "label": subnet.get("label", existing.get("label", "")),
            "item_type": subnet.get("item_type", existing.get("item_type", "")),
            "notes": subnet.get("notes", existing.get("notes")),
            "updated_at": _utcnow_iso(),
        }
        record.setdefault("created_at", _utcnow_iso())

        self._subnets[subnet_id] = record
        await self._async_persist()
        return record

    async def async_delete_subnet(self, subnet_id: str) -> None:
        """Delete a subnet, re-parenting its children to its own parent."""
        removed = self._subnets.get(subnet_id)
        if removed is None:
            return

        for child in self._subnets.values():
            if child.get("parent_id") == subnet_id:
                child["parent_id"] = removed.get("parent_id")

        del self._subnets[subnet_id]
        await self._async_persist()

    async def async_set_device_override(
        self, device_id: str, subnet_id: str | None
    ) -> None:
        if subnet_id is None:
            self._device_overrides.pop(device_id, None)
        else:
            self._device_overrides[device_id] = subnet_id
        await self._async_persist()
