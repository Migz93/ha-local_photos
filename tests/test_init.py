"""Tests for config-entry migrations."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_photos import async_migrate_entry
from custom_components.local_photos.const import CONF_MAXIMUM_FILE_SIZE, DOMAIN
from homeassistant.core import HomeAssistant


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stored_value", "expected_value"),
    [("20", "50"), ("50", "50"), ("100", "100"), (None, "50")],
)
async def test_migrate_source_size_limit(
    hass: HomeAssistant,
    stored_value: str | None,
    expected_value: str,
) -> None:
    """Existing entries receive the approved source-size migration."""
    options = {} if stored_value is None else {CONF_MAXIMUM_FILE_SIZE: stored_value}
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=1, options=options)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.options[CONF_MAXIMUM_FILE_SIZE] == expected_value
    assert entry.minor_version == 2
