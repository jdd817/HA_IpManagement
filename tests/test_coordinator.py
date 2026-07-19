from custom_components.ip_management.coordinator import scannable_subnets


def test_scannable_subnets_filters_to_opted_in_only():
    subnets = [
        {"id": "a", "cidr": "192.168.1.0/24", "active_scan_enabled": True},
        {"id": "b", "cidr": "192.168.2.0/24", "active_scan_enabled": False},
        {"id": "c", "cidr": "192.168.3.0/24"},  # missing flag entirely
    ]

    result = scannable_subnets(subnets)

    assert [s["id"] for s in result] == ["a"]


def test_scannable_subnets_empty_when_none_opted_in():
    subnets = [{"id": "a", "cidr": "192.168.1.0/24", "active_scan_enabled": False}]
    assert scannable_subnets(subnets) == []
