"""Regression tests for Local Photos image coordination."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_photos.api import Album, MediaItem
from custom_components.local_photos.const import DOMAIN
from custom_components.local_photos.coordinator.base import LocalPhotosDataUpdateCoordinator
from homeassistant.core import HomeAssistant


class FakePhotosManager:
    """Minimal photo manager with an optionally paused media scan."""

    def __init__(
        self,
        media_items: list[MediaItem],
        pause_scan: bool = False,
        pause_media_lookup: bool = False,
    ) -> None:
        """Initialize the fake manager."""
        self.album = Album("ALL", "All", "")
        self.media_items = media_items
        self.get_media_items_calls = 0
        self.scan_started = asyncio.Event()
        self.release_scan = asyncio.Event()
        self.media_lookup_started = asyncio.Event()
        self.release_media_lookup = asyncio.Event()
        if not pause_scan:
            self.release_scan.set()
        if not pause_media_lookup:
            self.release_media_lookup.set()

    def get_album(self, album_id: str) -> Album | None:
        """Return the test album."""
        return self.album if album_id == self.album.id else None

    async def get_media_items(self, album_id: str) -> list[MediaItem]:
        """Return test media after an optional controlled pause."""
        assert album_id == self.album.id
        self.get_media_items_calls += 1
        self.scan_started.set()
        await self.release_scan.wait()
        return self.media_items

    async def get_media_item(self, album_id: str, media_id: str) -> MediaItem | None:
        """Return a media item by ID."""
        assert album_id == self.album.id
        self.media_lookup_started.set()
        await self.release_media_lookup.wait()
        return next((item for item in self.media_items if item.id == media_id), None)


def _create_media_item(tmp_path: Path, identifier: str, size: tuple[int, int] = (160, 90)) -> MediaItem:
    """Create a JPEG media item for Combine mode."""
    path = tmp_path / f"{identifier}.jpg"
    Image.new("RGB", size, "white").save(path)
    return MediaItem(identifier, path.name, str(path))


def _create_coordinator(
    hass: HomeAssistant,
    manager: FakePhotosManager,
) -> LocalPhotosDataUpdateCoordinator:
    """Create a coordinator using the test manager."""
    entry = MockConfigEntry(domain=DOMAIN, title="Test", options={})
    return LocalPhotosDataUpdateCoordinator(hass, manager, entry, "ALL")


@pytest.mark.unit
async def test_concurrent_combine_requests_share_secondary_scan(hass: HomeAssistant, tmp_path: Path) -> None:
    """Concurrent Combine requests select a secondary image only once."""
    primary = _create_media_item(tmp_path, "primary")
    secondary = _create_media_item(tmp_path, "secondary")
    manager = FakePhotosManager([primary, secondary])
    coordinator = _create_coordinator(hass, manager)
    coordinator.current_media_primary = primary

    results = await asyncio.gather(
        coordinator._get_combined_media_data(245, 328),  # noqa: SLF001
        coordinator._get_combined_media_data(245, 328),  # noqa: SLF001
    )

    assert manager.get_media_items_calls == 1
    assert coordinator.current_media_secondary is secondary
    assert all(results)


@pytest.mark.unit
async def test_media_change_waits_for_secondary_selection(hass: HomeAssistant, tmp_path: Path) -> None:
    """Changing primary media cannot retain a secondary image from an older scan."""
    primary = _create_media_item(tmp_path, "primary")
    secondary = _create_media_item(tmp_path, "secondary")
    replacement = _create_media_item(tmp_path, "replacement")
    manager = FakePhotosManager(
        [primary, secondary, replacement],
        pause_scan=True,
        pause_media_lookup=True,
    )
    coordinator = _create_coordinator(hass, manager)
    coordinator.current_media_primary = primary

    image_task = asyncio.create_task(coordinator._get_combined_media_data(245, 328))  # noqa: SLF001
    await manager.scan_started.wait()
    media_change_task = asyncio.create_task(coordinator.set_current_media_with_id(replacement.id))
    await manager.media_lookup_started.wait()

    manager.release_media_lookup.set()
    await asyncio.sleep(0)

    assert coordinator.current_media_primary is primary

    manager.release_scan.set()
    await asyncio.gather(image_task, media_change_task)

    assert coordinator.current_media_primary is replacement
    assert coordinator.current_media_secondary is None
    assert not coordinator._secondary_media_selection_attempted  # noqa: SLF001


@pytest.mark.unit
async def test_secondary_selection_recalculates_basis_after_primary_change(hass: HomeAssistant, tmp_path: Path) -> None:
    """A secondary image is never selected using the previous primary's orientation."""
    primary = _create_media_item(tmp_path, "primary")
    secondary = _create_media_item(tmp_path, "secondary")
    replacement = _create_media_item(tmp_path, "replacement", (90, 160))
    manager = FakePhotosManager([primary, secondary, replacement])
    coordinator = _create_coordinator(hass, manager)
    coordinator.current_media_primary = primary
    initial_basis_captured = asyncio.Event()
    dimensions_calls = 0

    async def get_media_dimensions() -> tuple[float, float]:
        nonlocal dimensions_calls
        dimensions_calls += 1
        if dimensions_calls == 1:
            initial_basis_captured.set()
            return 160.0, 90.0
        return 90.0, 160.0

    await coordinator._secondary_media_selection_lock.acquire()  # noqa: SLF001
    with patch.object(coordinator, "_get_media_dimensions", new=get_media_dimensions):
        try:
            image_task = asyncio.create_task(coordinator._get_combined_media_data(245, 328))  # noqa: SLF001
            await initial_basis_captured.wait()

            # Simulate the state left by a completed primary-media change immediately
            # before this request acquires the selection lock.
            coordinator.current_media_primary = replacement
            coordinator.current_media_secondary = None
            coordinator._secondary_media_selection_attempted = False  # noqa: SLF001
        finally:
            coordinator._secondary_media_selection_lock.release()  # noqa: SLF001

        assert await image_task is None
    assert dimensions_calls == 2
    assert coordinator.current_media_secondary is None
    assert not coordinator._secondary_media_selection_attempted  # noqa: SLF001
