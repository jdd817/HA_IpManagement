"""Tests for SubnetStore, using a fake in-memory Store instead of a real hass."""
import asyncio

import pytest

from custom_components.ip_management import storage as storage_module
from custom_components.ip_management.storage import SubnetStore
from custom_components.ip_management.subnet_utils import InvalidCidrError


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
            {"cidr": "192.168.1.0/24", "label": "Home", "item_type": "trusted"}
        )
    )

    assert record["cidr"] == "192.168.1.0/24"
    assert record["label"] == "Home"
    assert record["parent_id"] is None
    assert record["active_scan_enabled"] is False
    assert store.subnets == [record]


def test_active_scan_enabled_defaults_to_false_and_can_be_opted_in():
    store = make_store()
    run(store.async_load())

    default_record = run(store.async_save_subnet({"cidr": "192.168.1.0/24"}))
    assert default_record["active_scan_enabled"] is False

    opted_in = run(
        store.async_save_subnet({"cidr": "192.168.2.0/24", "active_scan_enabled": True})
    )
    assert opted_in["active_scan_enabled"] is True


def test_active_scan_enabled_is_preserved_when_updating_other_fields():
    store = make_store()
    run(store.async_load())

    record = run(
        store.async_save_subnet({"cidr": "192.168.1.0/24", "active_scan_enabled": True})
    )

    updated = run(
        store.async_save_subnet({"id": record["id"], "cidr": "192.168.1.0/24", "label": "Renamed"})
    )

    assert updated["active_scan_enabled"] is True
    assert updated["label"] == "Renamed"


def test_save_rejects_invalid_cidr():
    store = make_store()
    run(store.async_load())

    with pytest.raises(InvalidCidrError):
        run(store.async_save_subnet({"cidr": "not-a-cidr"}))


def test_parent_is_inferred_from_cidr_containment_regardless_of_save_order():
    store = make_store()
    run(store.async_load())

    # Child saved before its parent exists...
    child = run(store.async_save_subnet({"cidr": "192.168.1.128/25", "label": "IoT"}))
    assert child["parent_id"] is None  # no containing subnet yet

    # ...once the parent is added, the child is automatically re-parented.
    parent = run(store.async_save_subnet({"cidr": "192.168.1.0/24", "label": "Home"}))

    updated_child = next(s for s in store.subnets if s["id"] == child["id"])
    assert updated_child["parent_id"] == parent["id"]


def test_inserting_a_subnet_between_two_existing_ones_reparents_automatically():
    store = make_store()
    run(store.async_load())

    grandparent = run(store.async_save_subnet({"cidr": "10.0.0.0/8", "label": "All"}))
    child = run(
        store.async_save_subnet({"cidr": "10.1.1.0/24", "label": "Cameras"})
    )
    # Directly nested under the grandparent until now.
    assert next(s for s in store.subnets if s["id"] == child["id"])["parent_id"] == grandparent["id"]

    # Inserting a subnet "between" them should slot in and re-parent the child.
    middle = run(store.async_save_subnet({"cidr": "10.1.0.0/16", "label": "Site"}))

    updated_child = next(s for s in store.subnets if s["id"] == child["id"])
    assert middle["parent_id"] == grandparent["id"]
    assert updated_child["parent_id"] == middle["id"]


def test_editing_a_subnets_cidr_recomputes_its_place_in_the_hierarchy():
    store = make_store()
    run(store.async_load())

    home = run(store.async_save_subnet({"cidr": "192.168.1.0/24", "label": "Home"}))
    other = run(store.async_save_subnet({"cidr": "10.0.0.0/24", "label": "Other"}))
    assert other["parent_id"] is None

    # Re-save "other" with a cidr that now falls inside "home".
    updated = run(
        store.async_save_subnet(
            {"id": other["id"], "cidr": "192.168.1.64/26", "label": "Other"}
        )
    )

    assert updated["parent_id"] == home["id"]


def test_delete_subnet_reparents_children_to_grandparent():
    store = make_store()
    run(store.async_load())

    grandparent = run(store.async_save_subnet({"cidr": "10.0.0.0/8", "label": "All"}))
    parent = run(store.async_save_subnet({"cidr": "10.1.0.0/16", "label": "Site"}))
    child = run(store.async_save_subnet({"cidr": "10.1.1.0/24", "label": "Cameras"}))
    assert parent["parent_id"] == grandparent["id"]
    assert next(s for s in store.subnets if s["id"] == child["id"])["parent_id"] == parent["id"]

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
