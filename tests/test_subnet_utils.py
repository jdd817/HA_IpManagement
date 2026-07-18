import pytest

from custom_components.ip_management.subnet_utils import (
    InvalidCidrError,
    display_range,
    infer_parent_ids,
    ip_in_network,
    last_octet_range,
    most_specific_container,
    most_specific_match,
    normalize_cidr,
    parse_network,
)


def test_parse_network_valid():
    net = parse_network("192.168.1.0/24")
    assert str(net) == "192.168.1.0/24"


def test_parse_network_normalizes_host_bits():
    # 192.168.1.5/24 should be treated as the 192.168.1.0/24 network.
    net = parse_network("192.168.1.5/24")
    assert str(net) == "192.168.1.0/24"


def test_parse_network_invalid_raises():
    with pytest.raises(InvalidCidrError):
        parse_network("not-a-cidr")


def test_normalize_cidr():
    assert normalize_cidr("10.0.0.5/8") == "10.0.0.0/8"


@pytest.mark.parametrize(
    "cidr,expected",
    [
        ("192.168.1.0/24", (0, 255)),
        ("192.168.1.16/28", (16, 31)),
        ("192.168.1.128/25", (128, 255)),
        ("10.0.0.0/32", (0, 0)),
    ],
)
def test_last_octet_range(cidr, expected):
    r = last_octet_range(cidr)
    assert (r.start, r.end) == expected


def test_last_octet_range_none_for_short_prefix():
    assert last_octet_range("10.0.0.0/16") is None


def test_display_range_uses_last_octet_for_slash24_and_smaller():
    assert display_range("192.168.1.0/24") == ".0-.255"
    assert display_range("192.168.1.16/28") == ".16-.31"


def test_display_range_falls_back_to_full_hosts_for_large_blocks():
    assert display_range("10.0.0.0/16") == "10.0.0.0-10.0.255.255"


def test_most_specific_container_picks_smallest_enclosing_subnet():
    candidates = {"wide": "192.168.0.0/16", "narrow": "192.168.1.0/24"}
    assert most_specific_container("192.168.1.128/25", candidates) == "narrow"


def test_most_specific_container_no_match_returns_none():
    assert most_specific_container("10.0.0.0/24", {"a": "192.168.0.0/16"}) is None


def test_most_specific_container_excludes_equal_or_smaller_networks():
    # A same-size or more-specific "candidate" is never treated as a parent.
    candidates = {"same": "192.168.1.0/24", "smaller": "192.168.1.0/25"}
    assert most_specific_container("192.168.1.0/24", candidates) is None


def test_infer_parent_ids_simple_nesting():
    cidrs = {"a": "10.0.0.0/8", "b": "10.1.0.0/16", "c": "10.1.1.0/24"}
    parents = infer_parent_ids(cidrs)
    assert parents == {"a": None, "b": "a", "c": "b"}


def test_infer_parent_ids_inserting_between_existing_subnets_reparents_child():
    # "b" starts out as a direct child of "a"; inserting "mid" between them
    # should re-parent "b" under "mid", and "mid" under "a".
    cidrs = {"a": "10.0.0.0/8", "b": "10.1.1.0/24", "mid": "10.1.0.0/16"}
    parents = infer_parent_ids(cidrs)
    assert parents == {"a": None, "mid": "a", "b": "mid"}


def test_infer_parent_ids_unrelated_subnets_have_no_parent():
    cidrs = {"a": "192.168.1.0/24", "b": "10.0.0.0/24"}
    assert infer_parent_ids(cidrs) == {"a": None, "b": None}


def test_ip_in_network():
    assert ip_in_network("192.168.1.5", "192.168.1.0/24") is True
    assert ip_in_network("192.168.2.5", "192.168.1.0/24") is False


def test_ip_in_network_handles_bad_input_gracefully():
    assert ip_in_network("not-an-ip", "192.168.1.0/24") is False
    assert ip_in_network("192.168.1.5", "not-a-cidr") is False


def test_most_specific_match_prefers_smaller_subnet():
    candidates = ["192.168.0.0/16", "192.168.1.0/24", "192.168.1.128/25"]
    assert most_specific_match("192.168.1.200", candidates) == "192.168.1.128/25"


def test_most_specific_match_no_match_returns_none():
    assert most_specific_match("10.0.0.1", ["192.168.1.0/24"]) is None
