"""Tests for the inexpensive folder picker."""

from __future__ import annotations

from pathlib import Path

from custom_components.local_photos.config_flow_handler.validators import validate_folder_path
from homeassistant.core import HomeAssistant


async def test_folder_picker_lists_directories_without_recursive_counts(hass: HomeAssistant, tmp_path: Path) -> None:
    """The picker does not walk every album merely to calculate a label."""
    (tmp_path / "iCloud").mkdir()
    (tmp_path / "iCloud-Favourites").mkdir()
    (tmp_path / "iCloud" / "nested.jpg").write_bytes(b"not read by this validation")

    assert await validate_folder_path(hass, str(tmp_path)) == {
        "ALL": "All Photos",
        "iCloud": "iCloud",
        "iCloud-Favourites": "iCloud-Favourites",
    }
