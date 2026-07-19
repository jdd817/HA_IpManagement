"""Tests for DeviceMatcher, using fakes for the HA registries/states it reads.

`DeviceMatcher`'s public methods are plain (synchronous) functions despite
the HA `async_`-prefix naming convention, so no event loop is needed here.
"""
from types import SimpleNamespace

import pytest

from homeassistant.helpers import device_registry as real_dr

from custom_components.ip_management import device_matcher as device_matcher_module
from custom_components.ip_management.device_matcher import DeviceIpInfo, DeviceMatcher, DiscoveredHost


class FakeDeviceEntry:
    def __init__(self, id, name=None, name_by_user=None, connections=None):
        self.id = id
        self.name = name
        self.name_by_user = name_by_user
        self.connections = connections or set()


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

    def _async_get_device(connections=None, identifiers=None):
        if connections:
            for device in devices.values():
                if device.connections & connections:
                    return device
        return None

    fake_dr = SimpleNamespace(
        CONNECTION_NETWORK_MAC=real_dr.CONNECTION_NETWORK_MAC,
        format_mac=real_dr.format_mac,
        async_get=lambda hass: SimpleNamespace(
            async_get=lambda device_id: devices.get(device_id),
            async_get_device=_async_get_device,
        ),
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
    assert result["dev-1"].device_matched is True


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


def test_resolve_scan_result_matches_known_device_by_mac(registries):
    registries.devices["dev-1"] = FakeDeviceEntry(
        "dev-1",
        name="Printer",
        connections={(real_dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
    )
    hass = FakeHass()
    host = DiscoveredHost(ip="192.168.1.50", mac="AA:BB:CC:DD:EE:FF")

    info = DeviceMatcher(hass).resolve_scan_result(host, source="active_scan")

    assert info.device_id == "dev-1"
    assert info.name == "Printer"
    assert info.ip_address == "192.168.1.50"
    assert info.source == "active_scan"
    assert info.device_matched is True


def test_resolve_scan_result_unknown_mac_gets_synthetic_id(registries):
    hass = FakeHass()
    host = DiscoveredHost(ip="192.168.1.60", mac="11:22:33:44:55:66")

    info = DeviceMatcher(hass).resolve_scan_result(host, source="active_scan")

    assert info.device_id == "scan:192.168.1.60"
    assert info.name == "192.168.1.60"
    assert info.device_matched is False


def test_resolve_scan_result_no_mac_uses_hostname_if_present(registries):
    hass = FakeHass()
    host = DiscoveredHost(ip="192.168.1.70", mac=None, name="printer.local")

    info = DeviceMatcher(hass).resolve_scan_result(host, source="passive_scan")

    assert info.device_id == "scan:192.168.1.70"
    assert info.name == "printer.local"
    assert info.source == "passive_scan"
    assert info.device_matched is False


def test_apply_manual_ip_links_overrides_scan_sourced_entry(registries):
    registries.devices["dev-manual"] = FakeDeviceEntry("dev-manual", name="Manual Match")
    hass = FakeHass()
    device_ips = {
        "scan:192.168.1.80": DeviceIpInfo(
            device_id="scan:192.168.1.80",
            name="192.168.1.80",
            ip_address="192.168.1.80",
            source="active_scan",
            device_matched=False,
        )
    }

    result = DeviceMatcher(hass).apply_manual_ip_links(
        device_ips, {"192.168.1.80": "dev-manual"}
    )

    assert "scan:192.168.1.80" not in result
    assert result["dev-manual"].name == "Manual Match"
    assert result["dev-manual"].ip_address == "192.168.1.80"
    assert result["dev-manual"].source == "active_scan"
    assert result["dev-manual"].device_matched is True
    assert result["dev-manual"].manually_assigned is True


def test_apply_manual_ip_links_overrides_authoritative_source(registries):
    """A manual assignment must also be able to correct a device_tracker or
    config_entry match, not just scan results HA couldn't identify at all."""
    registries.devices["dev-correct"] = FakeDeviceEntry("dev-correct", name="Correct Device")
    hass = FakeHass()
    device_ips = {
        "dev-wrong": DeviceIpInfo(
            device_id="dev-wrong",
            name="Wrong Device",
            ip_address="192.168.1.81",
            source="device_tracker",
        )
    }

    result = DeviceMatcher(hass).apply_manual_ip_links(
        device_ips, {"192.168.1.81": "dev-correct"}
    )

    assert "dev-wrong" not in result
    assert result["dev-correct"].ip_address == "192.168.1.81"
    assert result["dev-correct"].source == "device_tracker"
    assert result["dev-correct"].manually_assigned is True


def test_apply_manual_ip_links_ignores_link_to_unknown_device(registries):
    hass = FakeHass()
    device_ips = {
        "dev-1": DeviceIpInfo(
            device_id="dev-1", name="Known", ip_address="192.168.1.82", source="device_tracker"
        )
    }

    result = DeviceMatcher(hass).apply_manual_ip_links(
        device_ips, {"192.168.1.82": "nonexistent-device"}
    )

    assert result == device_ips


def test_apply_manual_ip_links_no_op_when_no_links(registries):
    hass = FakeHass()
    device_ips = {
        "dev-1": DeviceIpInfo(
            device_id="dev-1", name="Known", ip_address="192.168.1.83", source="device_tracker"
        )
    }

    result = DeviceMatcher(hass).apply_manual_ip_links(device_ips, {})

    assert result == device_ips


def test_match_devices_to_subnets_accepts_premerged_device_ips(registries):
    hass = FakeHass()
    subnets = [{"id": "narrow", "cidr": "192.168.1.0/24"}]
    device_ips = {
        "scan:192.168.1.77": DeviceIpInfo(
            device_id="scan:192.168.1.77",
            name="192.168.1.77",
            ip_address="192.168.1.77",
            source="active_scan",
            device_matched=False,
        )
    }

    matches = DeviceMatcher(hass).async_match_devices_to_subnets(
        subnets, device_overrides={}, device_ips=device_ips
    )

    assert len(matches) == 1
    assert matches[0]["device_id"] == "scan:192.168.1.77"
    assert matches[0]["subnet_id"] == "narrow"
    assert matches[0]["source"] == "active_scan"
    assert matches[0]["device_matched"] is False
