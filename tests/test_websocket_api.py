"""Tests for the websocket API command handlers.

Regression coverage for a real bug: every websocket message already carries
a reserved, auto-assigned numeric "id" field used for request/response
correlation (added client-side by `connection.sendMessagePromise`). The
save/delete handlers must read the subnet's id from a differently-named
field ("subnet_id"), not "id" — otherwise the envelope id silently clobbers
it before the handler ever sees it.

`@websocket_api.async_response` reschedules the decorated coroutine onto a
background task via `hass.async_create_background_task`, which needs a real
HomeAssistant instance to run. `functools.wraps` (used internally by that
decorator) leaves the original coroutine reachable via `__wrapped__`, so
tests call that directly to exercise the real handler logic without needing
a full hass/event-loop setup.
"""
import asyncio
from types import SimpleNamespace

import pytest

from custom_components.ip_management import storage as storage_module
from custom_components.ip_management import websocket_api as ws_module
from custom_components.ip_management.const import DOMAIN
from custom_components.ip_management.device_matcher import DeviceIpInfo, DiscoveredHost
from custom_components.ip_management.storage import SubnetStore


class FakeBackingStore:
    """Stands in for homeassistant.helpers.storage.Store."""

    def __init__(self, hass, version, key):
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


class FakeConnection:
    def __init__(self):
        self.results = []
        self.errors = []

    def send_result(self, msg_id, result=None):
        self.results.append((msg_id, result))

    def send_error(self, msg_id, code, message):
        self.errors.append((msg_id, code, message))


def run(coro):
    return asyncio.run(coro)


def real(handler):
    """Unwrap @websocket_api.async_response to the plain coroutine function."""
    return handler.__wrapped__


@pytest.fixture
def hass_and_store(monkeypatch):
    monkeypatch.setattr(storage_module, "Store", FakeBackingStore)
    store = SubnetStore(hass=object())
    run(store.async_load())
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": {"store": store, "matcher": None}}})
    return hass, store


def test_save_subnet_is_not_clobbered_by_envelope_id(hass_and_store):
    hass, store = hass_and_store
    connection = FakeConnection()
    # sendMessagePromise injects its own numeric "id" into every outgoing
    # message; a real client message looks like this.
    msg = {
        "type": "ip_management/subnets/save",
        "id": 115,
        "cidr": "192.168.1.0/24",
        "label": "Home",
    }

    run(real(ws_module.ws_save_subnet)(hass, connection, msg))

    assert len(store.subnets) == 1
    saved = store.subnets[0]
    assert saved["cidr"] == "192.168.1.0/24"
    assert saved["id"] != 115
    result_msg_id, result_payload = connection.results[0]
    assert result_msg_id == 115
    assert result_payload["subnet"]["id"] == saved["id"]


def test_save_subnet_updates_existing_record_via_subnet_id(hass_and_store):
    hass, store = hass_and_store
    connection = FakeConnection()
    create_msg = {"type": "ip_management/subnets/save", "id": 1, "cidr": "192.168.1.0/24", "label": "Home"}
    run(real(ws_module.ws_save_subnet)(hass, connection, create_msg))
    subnet_id = connection.results[0][1]["subnet"]["id"]

    update_msg = {
        "type": "ip_management/subnets/save",
        "id": 116,
        "subnet_id": subnet_id,
        "cidr": "192.168.1.0/24",
        "label": "Renamed",
    }
    run(real(ws_module.ws_save_subnet)(hass, connection, update_msg))

    assert len(store.subnets) == 1
    assert store.subnets[0]["id"] == subnet_id
    assert store.subnets[0]["label"] == "Renamed"


def test_delete_subnet_uses_subnet_id_not_envelope_id(hass_and_store):
    hass, store = hass_and_store
    connection = FakeConnection()
    create_msg = {"type": "ip_management/subnets/save", "id": 1, "cidr": "192.168.1.0/24"}
    run(real(ws_module.ws_save_subnet)(hass, connection, create_msg))
    subnet_id = connection.results[0][1]["subnet"]["id"]

    delete_msg = {"type": "ip_management/subnets/delete", "id": 999, "subnet_id": subnet_id}
    run(real(ws_module.ws_delete_subnet)(hass, connection, delete_msg))

    assert store.subnets == []


class FakeMatcher:
    """Stands in for DeviceMatcher: records what ws_list_devices assembles
    for matching, so the merge/gap-fill logic can be tested in isolation
    from DeviceMatcher's own registry-lookup internals (covered separately
    in test_device_matcher.py)."""

    def __init__(self, device_ips, resolved_by_ip):
        self._device_ips = device_ips
        self._resolved_by_ip = resolved_by_ip
        self.match_calls = []

    def async_get_device_ips(self):
        return dict(self._device_ips)

    def resolve_scan_result(self, host, source):
        base = self._resolved_by_ip[host.ip]
        return DeviceIpInfo(
            device_id=base.device_id,
            name=base.name,
            ip_address=base.ip_address,
            source=source,
        )

    def async_match_devices_to_subnets(self, subnets, device_overrides, device_ips=None):
        self.match_calls.append(device_ips)
        return [
            {
                "device_id": info.device_id,
                "name": info.name,
                "ip_address": info.ip_address,
                "subnet_id": None,
                "source": info.source,
            }
            for info in (device_ips or {}).values()
        ]


def test_ws_list_devices_scan_results_fill_gaps_but_never_override(hass_and_store):
    hass, store = hass_and_store
    connection = FakeConnection()

    known = {
        "dev-1": DeviceIpInfo(
            device_id="dev-1", name="Known", ip_address="192.168.1.5", source="device_tracker"
        )
    }
    # Simulate: active scan sees the *same* device (MAC correlation resolves
    # it back to dev-1) as well as a genuinely new, unregistered device.
    resolved_by_ip = {
        "192.168.1.5": DeviceIpInfo(
            device_id="dev-1", name="Known", ip_address="192.168.1.5", source="device_tracker"
        ),
        "192.168.1.9": DeviceIpInfo(
            device_id="scan:192.168.1.9",
            name="192.168.1.9",
            ip_address="192.168.1.9",
            source="active_scan",
        ),
    }
    matcher = FakeMatcher(device_ips=known, resolved_by_ip=resolved_by_ip)
    hass.data[DOMAIN]["entry-1"]["matcher"] = matcher
    hass.data[DOMAIN]["entry-1"]["active_scan_coordinator"] = SimpleNamespace(
        data=[DiscoveredHost(ip="192.168.1.5"), DiscoveredHost(ip="192.168.1.9")]
    )
    hass.data[DOMAIN]["entry-1"]["passive_scanner"] = None

    msg = {"type": "ip_management/devices/list", "id": 42}
    run(real(ws_module.ws_list_devices)(hass, connection, msg))

    merged = matcher.match_calls[0]
    assert merged["dev-1"].source == "device_tracker"  # not overridden by the scan
    assert merged["scan:192.168.1.9"].ip_address == "192.168.1.9"
    assert merged["scan:192.168.1.9"].source == "active_scan"


def test_ws_list_devices_works_with_no_scanners_configured(hass_and_store):
    hass, store = hass_and_store
    connection = FakeConnection()
    matcher = FakeMatcher(device_ips={}, resolved_by_ip={})
    hass.data[DOMAIN]["entry-1"]["matcher"] = matcher
    # No "active_scan_coordinator"/"passive_scanner" keys at all - both
    # features disabled is the default; ws_list_devices must not KeyError.

    msg = {"type": "ip_management/devices/list", "id": 7}
    run(real(ws_module.ws_list_devices)(hass, connection, msg))

    assert connection.results[0][1] == {"devices": []}
