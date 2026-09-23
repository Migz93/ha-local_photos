"""Tests for catalog-backed, look-ahead photo coordination."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_photos.api import Album, LocalPhotosManager, MediaItem
from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    CONF_FOLDER_PATH,
    CONF_MAXIMUM_FILE_SIZE,
    DOMAIN,
    SETTING_CROP_MODE_COMBINED,
)
from custom_components.local_photos.coordinator.base import LocalPhotosDataUpdateCoordinator
from custom_components.local_photos.coordinator.image_processing import render_single
from homeassistant.core import HomeAssistant


class FakePhotosManager:
    """Minimal metadata catalog used by coordinator tests."""

    def __init__(self, media_items: list[MediaItem]) -> None:
        """Initialize a catalog containing the supplied assets."""
        self.album = Album("ALL", "All", "")
        self.album.media_items_count = len(media_items)
        self.media_items = media_items
        self.get_media_items_calls = 0

    def get_album(self, album_id: str) -> Album | None:
        """Return the sole test album."""
        return self.album if album_id == "ALL" else None

    async def get_media_items(self, album_id: str) -> list[MediaItem]:
        """Return catalogued items without a filesystem scan."""
        assert album_id == "ALL"
        self.get_media_items_calls += 1
        return self.media_items

    async def get_media_item(self, album_id: str, media_id: str) -> MediaItem | None:
        """Return an item by its stable ID."""
        assert album_id == "ALL"
        return next((item for item in self.media_items if item.id == media_id), None)


def _create_media_item(tmp_path: Path, identifier: str, size: tuple[int, int] = (160, 90)) -> MediaItem:
    """Create a JPEG source and matching catalog record."""
    path = tmp_path / f"{identifier}.jpg"
    Image.new("RGB", size, "white").save(path)
    return MediaItem(identifier, path.name, str(path), fingerprint=identifier, dimensions=size)


def _create_coordinator(hass: HomeAssistant, manager: FakePhotosManager) -> LocalPhotosDataUpdateCoordinator:
    """Build one coordinator using a fake catalog."""
    entry = MockConfigEntry(domain=DOMAIN, title="Test", options={})
    return LocalPhotosDataUpdateCoordinator(hass, manager, entry, "ALL")


@pytest.mark.unit
async def test_catalog_uses_relative_ids_and_skips_large_sources(hass: HomeAssistant, tmp_path: Path) -> None:
    """A scan handles duplicate filenames once and applies the byte guard once."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    Image.new("RGB", (10, 10), "white").save(first / "same.jpg")
    Image.new("RGB", (10, 10), "white").save(second / "same.jpg")
    (second / "large.jpg").write_bytes(b"x" * (51 * 1024 * 1024))
    manager = LocalPhotosManager(
        hass,
        {CONF_FOLDER_PATH: str(tmp_path), CONF_MAXIMUM_FILE_SIZE: "50"},
    )

    await manager.scan_albums()
    items = await manager.get_media_items("ALL")

    assert {item.id for item in items} == {"first/same.jpg", "second/same.jpg"}
    assert manager.skipped_count == 1


@pytest.mark.unit
async def test_catalog_scans_only_selected_album_roots(hass: HomeAssistant, tmp_path: Path) -> None:
    """An unselected sibling tree is not opened while building a merged catalog."""
    favorites = tmp_path / "iCloud-Favourites"
    steph = tmp_path / "StephPhotos"
    unselected = tmp_path / "iCloud"
    favorites.mkdir()
    steph.mkdir()
    unselected.mkdir()
    Image.new("RGB", (10, 10), "white").save(favorites / "favorite.jpg")
    Image.new("RGB", (10, 10), "white").save(steph / "steph.jpg")
    # If this tree were scanned, its invalid JPEG would be counted as skipped.
    (unselected / "never-opened.jpg").write_bytes(b"not a JPEG")
    manager = LocalPhotosManager(
        hass,
        {
            CONF_ALBUM_ID: ["iCloud-Favourites", "StephPhotos"],
            CONF_FOLDER_PATH: str(tmp_path),
            CONF_MAXIMUM_FILE_SIZE: "50",
        },
    )

    await manager.scan_albums()
    manager.register_merged_album(["iCloud-Favourites", "StephPhotos"], "merged", "Merged")

    assert await manager.get_media_items("ALL") == []
    assert {item.id for item in await manager.get_media_items("merged")} == {
        "iCloud-Favourites/favorite.jpg",
        "StephPhotos/steph.jpg",
    }
    assert manager.skipped_count == 0


@pytest.mark.unit
async def test_camera_data_is_prepared_before_request(hass: HomeAssistant, tmp_path: Path) -> None:
    """The camera returns the prepared frame without selecting another source."""
    manager = FakePhotosManager([_create_media_item(tmp_path, "primary")])
    coordinator = _create_coordinator(hass, manager)

    await coordinator.async_start()
    calls_after_start = manager.get_media_items_calls
    image = await coordinator.get_media_data(width=245, height=328)

    assert image is not None
    assert image.startswith(b"\xff\xd8")
    assert manager.get_media_items_calls == calls_after_start
    await coordinator.async_shutdown()


@pytest.mark.unit
async def test_combine_uses_catalogued_orientation_without_opening_candidates(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Combine chooses a matching catalog asset and prepares a next frame."""
    primary = _create_media_item(tmp_path, "primary", (90, 160))
    secondary = _create_media_item(tmp_path, "secondary", (90, 160))
    manager = FakePhotosManager([primary, secondary])
    coordinator = _create_coordinator(hass, manager)
    coordinator.set_crop_mode(SETTING_CROP_MODE_COMBINED)

    await coordinator.async_start()
    assert coordinator.current_media is not None
    assert coordinator.current_secondary_media is not None
    assert await coordinator.get_media_data() is not None
    await coordinator.async_shutdown()


@pytest.mark.unit
def test_crop_render_covers_the_entire_requested_frame(tmp_path: Path) -> None:
    """A decoder-sized source never leaves black padding on a crop render."""
    source = tmp_path / "small.jpg"
    Image.new("RGB", (160, 90), "white").save(source)

    rendered = render_single(str(source), 1920, 1200, crop=True)

    with Image.open(io.BytesIO(rendered)) as image:
        assert image.size == (1920, 1200)
        assert image.getpixel((960, 1199)) == (255, 255, 255)
