"""Tests for PassiveScanner, mocking the zeroconf/HA surface it touches.

Real mDNS traffic isn't practical to exercise in a test sandbox (no real
multicast network), so these cover: the pure name-extraction helper, the
add/update/remove state-change handling logic, and the start/stop lifecycle
- each with fakes standing in for zeroconf's AsyncServiceBrowser and HA's
shared instance.
"""
import asyncio
from types import SimpleNamespace

import pytest
from zeroconf import ServiceStateChange

from custom_components.ip_management import passive_scanner as passive_scanner_module
from custom_components.ip_management.passive_scanner import (
    PassiveScanner,
    friendly_name_from_service_info,
)


def run(coro):
    return asyncio.run(coro)


class FakeServiceInfo:
    def __init__(self, server, addresses):
        self.server = server
        self._addresses = addresses

    def parsed_addresses(self, version=None):
        return self._addresses


class FakeAsyncZeroconf:
    def __init__(self, service_info_by_name=None):
        self.zeroconf = "sync-zeroconf-instance"
        self._service_info_by_name = service_info_by_name or {}

    async def async_get_service_info(self, service_type, name, timeout=None):
        return self._service_info_by_name.get(name)


class FakeBrowser:
    instances = []

    def __init__(self, zeroconf, types_, handlers):
        self.zeroconf = zeroconf
        self.types = types_
        self.handlers = handlers
        self.cancelled = False
        FakeBrowser.instances.append(self)

    async def async_cancel(self):
        self.cancelled = True


class FakeHass:
    def async_create_task(self, coro, name=None, eager_start=True):
        return asyncio.get_event_loop().create_task(coro)


def test_friendly_name_prefers_server_hostname():
    info = FakeServiceInfo(server="printer.local.", addresses=["192.168.1.5"])
    assert friendly_name_from_service_info(info, "Printer._ipp._tcp.local.") == "printer.local"


def test_friendly_name_falls_back_to_service_name_when_no_server():
    info = FakeServiceInfo(server=None, addresses=["192.168.1.5"])
    assert (
        friendly_name_from_service_info(info, "Printer._ipp._tcp.local.") == "Printer"
    )


def test_resolve_adds_discovered_hosts_from_service_info(monkeypatch):
    fake_zc = FakeAsyncZeroconf(
        service_info_by_name={
            "Printer._ipp._tcp.local.": FakeServiceInfo(
                server="printer.local.", addresses=["192.168.1.5", "192.168.1.6"]
            )
        }
    )
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )
    scanner = PassiveScanner(FakeHass())

    run(scanner._async_resolve("_ipp._tcp.local.", "Printer._ipp._tcp.local."))

    hosts = {h.ip: h for h in scanner.snapshot()}
    assert hosts["192.168.1.5"].name == "printer.local"
    assert hosts["192.168.1.6"].name == "printer.local"
    assert hosts["192.168.1.5"].mac is None


def test_resolve_skips_when_service_info_unavailable(monkeypatch):
    fake_zc = FakeAsyncZeroconf(service_info_by_name={})
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )
    scanner = PassiveScanner(FakeHass())

    run(scanner._async_resolve("_ipp._tcp.local.", "Unknown._ipp._tcp.local."))

    assert scanner.snapshot() == []


def test_state_change_schedules_resolution_except_on_removal(monkeypatch):
    fake_zc = FakeAsyncZeroconf(
        service_info_by_name={
            "Printer._ipp._tcp.local.": FakeServiceInfo(
                server="printer.local.", addresses=["192.168.1.5"]
            )
        }
    )
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )

    async def scenario():
        scanner = PassiveScanner(FakeHass())

        scanner._on_service_state_change(
            None, "_ipp._tcp.local.", "Printer._ipp._tcp.local.", ServiceStateChange.Added
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert scanner.snapshot() != []

        removed_scanner = PassiveScanner(FakeHass())
        removed_scanner._on_service_state_change(
            None, "_ipp._tcp.local.", "Printer._ipp._tcp.local.", ServiceStateChange.Removed
        )
        await asyncio.sleep(0)
        assert removed_scanner.snapshot() == []

    run(scenario())


def test_start_creates_browser_with_curated_service_types(monkeypatch):
    FakeBrowser.instances.clear()
    monkeypatch.setattr(passive_scanner_module, "AsyncServiceBrowser", FakeBrowser)
    fake_zc = FakeAsyncZeroconf()
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )
    scanner = PassiveScanner(FakeHass())

    run(scanner.async_start())

    assert len(FakeBrowser.instances) == 1
    browser = FakeBrowser.instances[0]
    assert browser.zeroconf == "sync-zeroconf-instance"
    assert "_hap._tcp.local." in browser.types


def test_start_is_idempotent(monkeypatch):
    FakeBrowser.instances.clear()
    monkeypatch.setattr(passive_scanner_module, "AsyncServiceBrowser", FakeBrowser)
    fake_zc = FakeAsyncZeroconf()
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )
    scanner = PassiveScanner(FakeHass())

    run(scanner.async_start())
    run(scanner.async_start())

    assert len(FakeBrowser.instances) == 1


def test_stop_cancels_the_browser(monkeypatch):
    FakeBrowser.instances.clear()
    monkeypatch.setattr(passive_scanner_module, "AsyncServiceBrowser", FakeBrowser)
    fake_zc = FakeAsyncZeroconf()
    monkeypatch.setattr(
        passive_scanner_module.ha_zeroconf,
        "async_get_async_instance",
        lambda hass: fake_zc,
    )
    scanner = PassiveScanner(FakeHass())
    run(scanner.async_start())

    run(scanner.async_stop())

    assert FakeBrowser.instances[0].cancelled is True
