"""Tests for DeviceMatcher, using fakes for the HA registries/states it reads.

`DeviceMatcher`'s public methods are plain (synchronous) functions despite
the HA `async_`-prefix naming convention, so no event loop is needed here.
"""
from types import SimpleNamespace

import pytest

from custom_components.ip_management import device_matcher as device_matcher_module
from custom_components.ip_management.device_matcher import DeviceMatcher


class FakeDeviceEntry:
    def __init__(self, id, name=None, name_by_user=None):
        self.id = id
        self.name = name
        self.name_by_user = name_by_user


class FakeEntityEntry:
    def __init__(self, entity_id, device_id):
        self.entity_id = entity_id
        self.device_id = device_id


class FakeState:
    def __init__(self, entity_id, name, attributes):
        self.entity_id = entity_id
        self.name = name
        self.attributes = attributes


class FakeStates:
    def __init__(self, states):
        self._states = states

    def async_all(self, domain):
        return [s for s in self._states if s.entity_id.startswith(f"{domain}.")]


class FakeConfigEntry:
    def __init__(self, entry_id, data):
        self.entry_id = entry_id
        self.data = data


class FakeConfigEntries:
    def __init__(self, entries):
        self._entries = entries

    def async_entries(self):
        return self._entries


class FakeHass:
    def __init__(self, states=None, config_entries=None):
        self.states = FakeStates(states or [])
        self.config_entries = FakeConfigEntries(config_entries or [])


@pytest.fixture
def registries(monkeypatch):
    """Patch the module-level `dr`/`er` HA helper references with fakes."""
    devices = {}
    entities = {}
    devices_by_config_entry = {}

    fake_dr = SimpleNamespace(
        async_get=lambda hass: SimpleNamespace(async_get=lambda device_id: devices.get(device_id)),
        async_entries_for_config_entry=lambda dev_reg, entry_id: devices_by_config_entry.get(
            entry_id, []
        ),
    )
    fake_er = SimpleNamespace(
        async_get=lambda hass: SimpleNamespace(async_get=lambda entity_id: entities.get(entity_id)),
    )

    monkeypatch.setattr(device_matcher_module, "dr", fake_dr)
    monkeypatch.setattr(device_matcher_module, "er", fake_er)

    return SimpleNamespace(
        devices=devices, entities=entities, devices_by_config_entry=devices_by_config_entry
    )


def test_device_tracker_ip_resolved(registries):
    registries.devices["dev-1"] = FakeDeviceEntry("dev-1", name="Phone")
    registries.entities["device_tracker.phone"] = FakeEntityEntry(
        "device_tracker.phone", device_id="dev-1"
    )
    hass = FakeHass(
        states=[
            FakeState(
                "device_tracker.phone", "Phone", {"ip_address": "192.168.1.42"}
            )
        ]
    )

    result = DeviceMatcher(hass).async_get_device_ips()

    assert result["dev-1"].ip_address == "192.168.1.42"
    assert result["dev-1"].source == "device_tracker"
    assert result["dev-1"].name == "Phone"


def test_non_ipv4_attribute_ignored(registries):
    registries.devices["dev-1"] = FakeDeviceEntry("dev-1", name="Phone")
    registries.entities["device_tracker.phone"] = FakeEntityEntry(
        "device_tracker.phone", device_id="dev-1"
    )
    hass = FakeHass(
        states=[FakeState("device_tracker.phone", "Phone", {"ip_address": "home"})]
    )

    result = DeviceMatcher(hass).async_get_device_ips()

    assert result == {}


def test_config_entry_ip_used_as_fallback(registries):
    registries.devices["dev-2"] = FakeDeviceEntry("dev-2", name="Printer")
    registries.devices_by_config_entry["entry-1"] = [registries.devices["dev-2"]]
    hass = FakeHass(
        config_entries=[FakeConfigEntry("entry-1", {"host": "192.168.1.55"})]
    )

    result = DeviceMatcher(hass).async_get_device_ips()

    assert result["dev-2"].ip_address == "192.168.1.55"
    assert result["dev-2"].source == "config_entry"


def test_device_tracker_takes_priority_over_config_entry(registries):
    registries.devices["dev-3"] = FakeDeviceEntry("dev-3", name="Hub")
    registries.devices_by_config_entry["entry-1"] = [registries.devices["dev-3"]]
    registries.entities["device_tracker.hub"] = FakeEntityEntry(
        "device_tracker.hub", device_id="dev-3"
    )
    hass = FakeHass(
        states=[
            FakeState("device_tracker.hub", "Hub", {"ip_address": "192.168.1.99"})
        ],
        config_entries=[FakeConfigEntry("entry-1", {"host": "192.168.1.11"})],
    )

    result = DeviceMatcher(hass).async_get_device_ips()

    assert result["dev-3"].ip_address == "192.168.1.99"
    assert result["dev-3"].source == "device_tracker"


def test_match_devices_to_subnets_uses_most_specific_and_overrides(registries):
    registries.devices["dev-1"] = FakeDeviceEntry("dev-1", name="Camera")
    registries.entities["device_tracker.camera"] = FakeEntityEntry(
        "device_tracker.camera", device_id="dev-1"
    )
    registries.devices["dev-2"] = FakeDeviceEntry("dev-2", name="Unrouted")
    registries.entities["device_tracker.other"] = FakeEntityEntry(
        "device_tracker.other", device_id="dev-2"
    )
    hass = FakeHass(
        states=[
            FakeState(
                "device_tracker.camera", "Camera", {"ip_address": "192.168.1.200"}
            ),
            FakeState("device_tracker.other", "Unrouted", {"ip_address": "10.0.0.5"}),
        ]
    )
    subnets = [
        {"id": "wide", "cidr": "192.168.0.0/16"},
        {"id": "narrow", "cidr": "192.168.1.128/25"},
    ]

    matches = DeviceMatcher(hass).async_match_devices_to_subnets(
        subnets, device_overrides={}
    )
    by_device = {m["device_id"]: m for m in matches}

    assert by_device["dev-1"]["subnet_id"] == "narrow"
    assert by_device["dev-2"]["subnet_id"] is None


def test_device_override_takes_precedence_over_ip_match(registries):
    registries.devices["dev-1"] = FakeDeviceEntry("dev-1", name="Camera")
    registries.entities["device_tracker.camera"] = FakeEntityEntry(
        "device_tracker.camera", device_id="dev-1"
    )
    hass = FakeHass(
        states=[
            FakeState(
                "device_tracker.camera", "Camera", {"ip_address": "192.168.1.200"}
            )
        ]
    )
    subnets = [{"id": "narrow", "cidr": "192.168.1.128/25"}]

    matches = DeviceMatcher(hass).async_match_devices_to_subnets(
        subnets, device_overrides={"dev-1": "manual-subnet"}
    )

    assert matches[0]["subnet_id"] == "manual-subnet"
