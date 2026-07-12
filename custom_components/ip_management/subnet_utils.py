"""Pure-Python helpers for subnet CIDR math, nesting validation, and display.

Kept free of any Home Assistant imports so it can be unit tested in
isolation and reused by both the storage layer and the device matcher.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable


class InvalidCidrError(ValueError):
    """Raised when a CIDR string cannot be parsed as an IPv4 network."""


class SubnetNestingError(ValueError):
    """Raised when a child subnet is not fully contained within its parent."""


def parse_network(cidr: str) -> ipaddress.IPv4Network:
    """Parse a CIDR string, normalizing away stray host bits."""
    try:
        return ipaddress.IPv4Network(cidr, strict=False)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as err:
        raise InvalidCidrError(f"'{cidr}' is not a valid IPv4 CIDR block") from err


def normalize_cidr(cidr: str) -> str:
    """Return the canonical network-address form of a CIDR string."""
    return str(parse_network(cidr))


def validate_nesting(child_cidr: str, parent_cidr: str | None) -> None:
    """Raise if `child_cidr` is invalid, or not contained within `parent_cidr`."""
    child = parse_network(child_cidr)
    if parent_cidr is None:
        return
    parent = parse_network(parent_cidr)
    if not child.subnet_of(parent):
        raise SubnetNestingError(
            f"{child_cidr} is not contained within parent subnet {parent_cidr}"
        )


@dataclass(frozen=True)
class OctetRange:
    start: int
    end: int

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f".{self.start}-.{self.end}"


def last_octet_range(cidr: str) -> OctetRange | None:
    """Return the last-octet range for networks with prefix length >= 24.

    Returns None when the prefix is short enough that the block spans more
    than one third-octet group, where a single last-octet range would be
    misleading (e.g. a /16).
    """
    network = parse_network(cidr)
    if network.prefixlen < 24:
        return None
    return OctetRange(
        start=int(network.network_address) & 0xFF,
        end=int(network.broadcast_address) & 0xFF,
    )


def display_range(cidr: str) -> str:
    """Human-readable range string used by the UI.

    For /24-or-smaller networks this is the last-octet range (e.g. ".0-.255").
    For larger blocks (prefix < 24) it falls back to the full first/last host.
    """
    network = parse_network(cidr)
    octets = last_octet_range(cidr)
    if octets is not None:
        return str(octets)
    return f"{network.network_address}-{network.broadcast_address}"


def ip_in_network(ip: str, cidr: str) -> bool:
    """Return True if `ip` falls within `cidr`. Never raises on bad input."""
    try:
        address = ipaddress.IPv4Address(ip)
        network = parse_network(cidr)
    except (ipaddress.AddressValueError, InvalidCidrError):
        return False
    return address in network


def most_specific_match(ip: str, candidates: Iterable[str]) -> str | None:
    """Return the CIDR string from `candidates` with the smallest matching subnet."""
    matches = [c for c in candidates if ip_in_network(ip, c)]
    if not matches:
        return None
    return max(matches, key=lambda c: parse_network(c).prefixlen)
