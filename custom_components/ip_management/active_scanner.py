"""Active discovery: ping-sweeps subnets registered in the panel and reads
the system ARP/neighbor table to find a MAC address for whatever responds.

Only ever scans CIDRs the user has explicitly registered as a subnet (see
storage.py) — never a wider network than that. Subnets larger than
MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET hosts are skipped entirely (logged, not
scanned partially) so a mistakenly huge CIDR (e.g. a /8) can't turn into an
unbounded flood of the local network.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .const import MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET
from .device_matcher import DiscoveredHost
from .subnet_utils import parse_network

_LOGGER = logging.getLogger(__name__)

PING_CONCURRENCY = 32
PING_TIMEOUT_SECONDS = 1.0
ARP_COMMAND_TIMEOUT_SECONDS = 5.0

_IP_NEIGH_LINE = re.compile(
    r"^(?P<ip>\d+\.\d+\.\d+\.\d+)\s+dev\s+\S+.*?\blladdr\s+(?P<mac>[0-9a-fA-F:]+)",
    re.MULTILINE,
)
_ARP_A_POSIX_LINE = re.compile(
    r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:]+)", re.MULTILINE
)
_ARP_A_WINDOWS_LINE = re.compile(
    r"^\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s+(?P<mac>[0-9a-fA-F-]+)\s+\w+", re.MULTILINE
)


def hosts_to_scan(
    cidr: str, max_hosts: int = MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET
) -> list[str] | None:
    """Return every address in `cidr`, or None if that's more than `max_hosts`.

    Includes the network and broadcast addresses (i.e. every address
    `ipaddress.IPv4Network` iterates, not just `.hosts()`) — subnets in this
    app are arbitrary user-defined ranges for organizing IPs, not
    necessarily classful networks, so nothing about a CIDR's first/last
    address is assumed unusable. `subnet_utils.display_range` already shows
    users that full range (e.g. ".32-.47" for a /28 starting at .32), so the
    scan needs to cover it too, or it silently skips addresses the UI claims
    are part of the subnet.

    None signals "too big to scan safely" rather than raising, so callers
    can skip-and-log per subnet without aborting the whole sweep.
    `num_addresses` is used for the size check rather than materializing the
    full list first, so an oversized subnet is rejected without ever
    building a huge list.
    """
    network = parse_network(cidr)
    if network.num_addresses > max_hosts:
        return None
    return [str(ip) for ip in network]


def parse_ip_neigh_output(output: str) -> dict[str, str]:
    """Parse Linux `ip neigh show` output into {ip: mac}."""
    return {m.group("ip"): m.group("mac").lower() for m in _IP_NEIGH_LINE.finditer(output)}


def parse_arp_a_output(output: str) -> dict[str, str]:
    """Parse POSIX (BSD/macOS/net-tools) `arp -a` output into {ip: mac}."""
    return {
        m.group("ip"): m.group("mac").lower() for m in _ARP_A_POSIX_LINE.finditer(output)
    }


def parse_windows_arp_a_output(output: str) -> dict[str, str]:
    """Parse Windows `arp -a` output into {ip: mac}, normalizing '-' to ':'."""
    return {
        m.group("ip"): m.group("mac").lower().replace("-", ":")
        for m in _ARP_A_WINDOWS_LINE.finditer(output)
    }


def _ping_command(ip: str, timeout: float) -> list[str]:
    if platform.system() == "Windows":
        return ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    return ["ping", "-c", "1", "-W", str(max(1, int(round(timeout)))), ip]


async def _run_and_capture(args: list[str], timeout: float) -> str | None:
    """Run `args`, returning captured stdout, or None on any failure/timeout."""
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (OSError, asyncio.TimeoutError):
        return None
    if process.returncode != 0:
        return None
    return stdout.decode(errors="ignore")


async def async_ping(ip: str, timeout: float = PING_TIMEOUT_SECONDS) -> bool:
    """Return True if `ip` responds to a single ping. Never raises."""
    try:
        process = await asyncio.create_subprocess_exec(
            *_ping_command(ip, timeout),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return_code = await asyncio.wait_for(process.wait(), timeout=timeout + 2)
    except (OSError, asyncio.TimeoutError):
        return False
    return return_code == 0


async def async_read_arp_table() -> dict[str, str]:
    """Return {ip: mac} from the system's ARP/neighbor cache. Never raises."""
    if platform.system() == "Windows":
        commands = [(["arp", "-a"], parse_windows_arp_a_output)]
    else:
        commands = [
            (["ip", "neigh", "show"], parse_ip_neigh_output),
            (["arp", "-a"], parse_arp_a_output),
        ]

    for args, parser in commands:
        output = await _run_and_capture(args, ARP_COMMAND_TIMEOUT_SECONDS)
        if output is None:
            continue
        table = parser(output)
        if table:
            return table
    return {}


class ActiveScanner:
    """Ping-sweeps registered subnets and correlates responses via ARP."""

    def __init__(
        self,
        hass: HomeAssistant,
        ping_fn=async_ping,
        arp_table_fn=async_read_arp_table,
    ) -> None:
        self._hass = hass
        self._ping_fn = ping_fn
        self._arp_table_fn = arp_table_fn

    async def async_scan(self, subnets: list[dict[str, Any]]) -> list[DiscoveredHost]:
        """Ping-sweep every registered subnet and return the hosts that responded."""
        all_ips: set[str] = set()
        for subnet in subnets:
            ips = hosts_to_scan(subnet["cidr"])
            if ips is None:
                _LOGGER.warning(
                    "Skipping active scan of %s: larger than %d hosts",
                    subnet["cidr"],
                    MAX_ACTIVE_SCAN_HOSTS_PER_SUBNET,
                )
                continue
            all_ips.update(ips)

        if not all_ips:
            return []

        semaphore = asyncio.Semaphore(PING_CONCURRENCY)

        async def _ping_bounded(ip: str) -> tuple[str, bool]:
            async with semaphore:
                return ip, await self._ping_fn(ip)

        results = await asyncio.gather(*(_ping_bounded(ip) for ip in all_ips))
        alive_ips = {ip for ip, is_alive in results if is_alive}
        if not alive_ips:
            return []

        arp_table = await self._arp_table_fn()
        return [DiscoveredHost(ip=ip, mac=arp_table.get(ip)) for ip in sorted(alive_ips)]
