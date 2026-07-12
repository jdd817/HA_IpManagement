"""Tests for SubnetStore, using a fake in-memory Store instead of a real hass."""
import asyncio

import pytest

from custom_components.ip_management import storage as storage_module
from custom_components.ip_management.storage import SubnetStore
from custom_components.ip_management.subnet_utils import (
    InvalidCidrError,
    SubnetNestingError,
)


class FakeStore:
    """Stands in for homeassistant.helpers.storage.Store."""

    def __init__(self, hass, version, key):
        self.hass = hass
        self.version = version
        self.key = key
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    monkeypatch.setattr(storage_module, "Store", FakeStore)


def run(coro):
    return asyncio.run(coro)


def make_store():
    return SubnetStore(hass=object())


def test_save_and_list_subnet():
    store = make_store()
    run(store.async_load())

    record = run(
        store.async_save_subnet(
            {"cidr": "192.168.1.0/24", "parent_id": None, "label": "Home", "item_type": "trusted"}
        )
    )

    assert record["cidr"] == "192.168.1.0/24"
    assert record["label"] == "Home"
    assert store.subnets == [record]


def test_save_rejects_invalid_cidr():
    store = make_store()
    run(store.async_load())

    with pytest.raises(InvalidCidrError):
        run(store.async_save_subnet({"cidr": "not-a-cidr", "parent_id": None}))


def test_save_rejects_child_not_within_parent():
    store = make_store()
    run(store.async_load())

    parent = run(store.async_save_subnet({"cidr": "192.168.1.0/24"}))

    with pytest.raises(SubnetNestingError):
        run(
            store.async_save_subnet(
                {"cidr": "192.168.2.0/25", "parent_id": parent["id"]}
            )
        )


def test_save_rejects_self_parent():
    store = make_store()
    run(store.async_load())

    record = run(store.async_save_subnet({"cidr": "192.168.1.0/24"}))

    with pytest.raises(SubnetNestingError):
        run(
            store.async_save_subnet(
                {"id": record["id"], "cidr": "192.168.1.0/24", "parent_id": record["id"]}
            )
        )


def test_nested_subnet_accepted():
    store = make_store()
    run(store.async_load())

    parent = run(store.async_save_subnet({"cidr": "192.168.1.0/24", "label": "Home"}))
    child = run(
        store.async_save_subnet(
            {"cidr": "192.168.1.128/25", "parent_id": parent["id"], "label": "IoT"}
        )
    )

    assert child["parent_id"] == parent["id"]


def test_delete_subnet_reparents_children_to_grandparent():
    store = make_store()
    run(store.async_load())

    grandparent = run(store.async_save_subnet({"cidr": "10.0.0.0/8", "label": "All"}))
    parent = run(
        store.async_save_subnet(
            {"cidr": "10.1.0.0/16", "parent_id": grandparent["id"], "label": "Site"}
        )
    )
    child = run(
        store.async_save_subnet(
            {"cidr": "10.1.1.0/24", "parent_id": parent["id"], "label": "Cameras"}
        )
    )

    run(store.async_delete_subnet(parent["id"]))

    remaining_ids = {s["id"] for s in store.subnets}
    assert parent["id"] not in remaining_ids
    updated_child = next(s for s in store.subnets if s["id"] == child["id"])
    assert updated_child["parent_id"] == grandparent["id"]


def test_persists_across_reload_via_same_backing_store():
    store = make_store()
    run(store.async_load())
    run(store.async_save_subnet({"cidr": "192.168.1.0/24", "label": "Home"}))

    reloaded = SubnetStore(hass=object())
    reloaded._store = store._store  # share the fake backing store
    run(reloaded.async_load())

    assert len(reloaded.subnets) == 1
    assert reloaded.subnets[0]["label"] == "Home"


def test_device_override_set_and_clear():
    store = make_store()
    run(store.async_load())

    run(store.async_set_device_override("device-1", "subnet-a"))
    assert store.device_overrides == {"device-1": "subnet-a"}

    run(store.async_set_device_override("device-1", None))
    assert store.device_overrides == {}
