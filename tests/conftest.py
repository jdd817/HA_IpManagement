"""Shared pytest fixtures for IP Management tests.

Tests avoid spinning up a real Home Assistant Core instance. `storage.py`
and `device_matcher.py` are exercised through lightweight fakes standing in
for the small slice of the HA API they use (Store, device/entity registry,
states, config_entries) rather than a full `hass` fixture — this keeps the
suite fast and avoids depending on HA's event-loop/socket setup, which
needs a real, unrestricted asyncio environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
