import asyncio

import pytest

from custom_components.ip_management.active_scanner import (
    ActiveScanner,
    hosts_to_scan,
    parse_arp_a_output,
    parse_ip_neigh_output,
    parse_windows_arp_a_output,
)
from custom_components.ip_management.device_matcher import DiscoveredHost


def run(coro):
    return asyncio.run(coro)


def test_hosts_to_scan_returns_every_address_including_network_and_broadcast():
    # Subnets here are arbitrary user-defined ranges, not classful networks -
    # display_range already shows users the network/broadcast addresses as
    # part of the range (e.g. ".0-.3"), so the scan must cover them too.
    ips = hosts_to_scan("192.168.1.0/30", max_hosts=512)
    assert ips == ["192.168.1.0", "192.168.1.1", "192.168.1.2", "192.168.1.3"]


def test_hosts_to_scan_does_not_skip_the_first_address_of_the_block():
    # Regression test: 10.72.10.32/28 was silently skipping 10.72.10.32
    # (the network address) before hosts_to_scan switched from
    # network.hosts() to iterating the full network.
    ips = hosts_to_scan("10.72.10.32/28", max_hosts=512)
    assert ips[0] == "10.72.10.32"
    assert ips[-1] == "10.72.10.47"
    assert len(ips) == 16


def test_hosts_to_scan_slash32_returns_the_single_address():
    assert hosts_to_scan("192.168.1.5/32", max_hosts=512) == ["192.168.1.5"]


def test_hosts_to_scan_rejects_subnets_over_the_cap():
    # A /16 has 65536 addresses - far past a small cap.
    assert hosts_to_scan("10.0.0.0/16", max_hosts=512) is None


def test_hosts_to_scan_accepts_subnets_at_the_cap():
    # A /24 has exactly 256 addresses (network + broadcast included).
    assert len(hosts_to_scan("192.168.1.0/24", max_hosts=256)) == 256


def test_parse_ip_neigh_output():
    output = (
        "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff STALE\n"
        "192.168.1.2 dev eth0  FAILED\n"
        "192.168.1.3 dev eth0 lladdr 11:22:33:44:55:66 REACHABLE\n"
    )
    assert parse_ip_neigh_output(output) == {
        "192.168.1.1": "aa:bb:cc:dd:ee:ff",
        "192.168.1.3": "11:22:33:44:55:66",
    }


def test_parse_arp_a_output_posix():
    output = (
        "router.local (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]\n"
        "? (192.168.1.2) at (incomplete) on en0 ifscope [ethernet]\n"
    )
    assert parse_arp_a_output(output) == {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}


def test_parse_windows_arp_a_output():
    output = (
        "Interface: 192.168.1.100 --- 0x3\n"
        "  Internet Address      Physical Address      Type\n"
        "  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic\n"
        "  192.168.1.255         ff-ff-ff-ff-ff-ff     static\n"
    )
    result = parse_windows_arp_a_output(output)
    assert result["192.168.1.1"] == "aa:bb:cc:dd:ee:ff"
    assert result["192.168.1.255"] == "ff:ff:ff:ff:ff:ff"


def test_scan_pings_hosts_in_registered_subnets_and_resolves_mac():
    pinged = []

    async def fake_ping(ip):
        pinged.append(ip)
        return ip == "192.168.1.1"

    async def fake_arp_table():
        return {"192.168.1.1": "aa:bb:cc:dd:ee:ff"}

    scanner = ActiveScanner(hass=object(), ping_fn=fake_ping, arp_table_fn=fake_arp_table)
    subnets = [{"id": "s1", "cidr": "192.168.1.0/30"}]

    hosts = run(scanner.async_scan(subnets))

    assert sorted(pinged) == [
        "192.168.1.0",
        "192.168.1.1",
        "192.168.1.2",
        "192.168.1.3",
    ]
    assert hosts == [DiscoveredHost(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff")]


def test_scan_skips_oversized_subnets_without_pinging_them(caplog):
    pinged = []

    async def fake_ping(ip):
        pinged.append(ip)
        return True

    async def fake_arp_table():
        return {}

    scanner = ActiveScanner(hass=object(), ping_fn=fake_ping, arp_table_fn=fake_arp_table)
    subnets = [{"id": "s1", "cidr": "10.0.0.0/16"}]

    hosts = run(scanner.async_scan(subnets))

    assert pinged == []
    assert hosts == []


def test_scan_returns_empty_when_nothing_responds():
    async def fake_ping(ip):
        return False

    async def fake_arp_table():
        raise AssertionError("arp table should not be read if nothing responded")

    scanner = ActiveScanner(hass=object(), ping_fn=fake_ping, arp_table_fn=fake_arp_table)
    subnets = [{"id": "s1", "cidr": "192.168.1.0/30"}]

    hosts = run(scanner.async_scan(subnets))

    assert hosts == []
