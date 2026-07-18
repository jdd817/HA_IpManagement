"""Pure-Python helpers for subnet CIDR math, nesting inference, and display.

Kept free of any Home Assistant imports so it can be unit tested in
isolation and reused by both the storage layer and the device matcher.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable, Mapping


class InvalidCidrError(ValueError):
    """Raised when a CIDR string cannot be parsed as an IPv4 network."""


def parse_network(cidr: str) -> ipaddress.IPv4Network:
    """Parse a CIDR string, normalizing away stray host bits."""
    try:
        return ipaddress.IPv4Network(cidr, strict=False)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as err:
        raise InvalidCidrError(f"'{cidr}' is not a valid IPv4 CIDR block") from err


def normalize_cidr(cidr: str) -> str:
    """Return the canonical network-address form of a CIDR string."""
    return str(parse_network(cidr))


def most_specific_container(cidr: str, candidates: Mapping[str, str]) -> str | None:
    """Return the id from `candidates` (id -> cidr) whose network is the
    smallest one that strictly contains `cidr`, or None if none do.

    "Strictly contains" excludes equal-sized or smaller (more specific)
    networks, so a subnet is never considered its own parent.
    """
    network = parse_network(cidr)
    best_id: str | None = None
    best_prefixlen = -1
    for candidate_id, candidate_cidr in candidates.items():
        candidate_network = parse_network(candidate_cidr)
        if candidate_network.prefixlen >= network.prefixlen:
            continue
        if network.subnet_of(candidate_network) and candidate_network.prefixlen > best_prefixlen:
            best_prefixlen = candidate_network.prefixlen
            best_id = candidate_id
    return best_id


def infer_parent_ids(cidrs_by_id: Mapping[str, str]) -> dict[str, str | None]:
    """Infer parent/child nesting for a set of subnets from CIDR containment
    alone: each subnet's parent is the most specific *other* subnet that
    strictly contains it.

    Recomputing every subnet's parent from scratch (rather than patching
    just the one being added/edited) means inserting a subnet "between" two
    existing ones automatically re-parents the more specific one — there is
    no user-settable parent field to keep in sync.
    """
    return {
        subnet_id: most_specific_container(
            cidr, {i: c for i, c in cidrs_by_id.items() if i != subnet_id}
        )
        for subnet_id, cidr in cidrs_by_id.items()
    }


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
