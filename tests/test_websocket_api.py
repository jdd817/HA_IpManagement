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
