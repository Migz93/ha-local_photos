"""Tests for the background catalog scan."""

from __future__ import annotations

from contextlib import AbstractContextManager
import io
from pathlib import Path
import threading
from unittest.mock import patch

from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_photos.api import LocalPhotosDirectoryNotFoundError, LocalPhotosManager, MediaItem
from custom_components.local_photos.const import CONF_FOLDER_PATH, CONF_MAXIMUM_FILE_SIZE, DOMAIN
from custom_components.local_photos.coordinator.base import LocalPhotosDataUpdateCoordinator
from custom_components.local_photos.coordinator.image_processing import render_single
from homeassistant.core import HomeAssistant


def _create_photos(folder: Path, count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        Image.new("RGB", (160, 90), "white").save(folder / f"photo-{index:02}.jpg")


def _hold_scan_until(release: threading.Event) -> AbstractContextManager[object]:
    """Keep the scan worker waiting at its first photo until released."""
    real_open = Image.open

    def blocked_open(path: Path) -> Image.Image:
        release.wait(timeout=10)
        return real_open(path)

    return patch("custom_components.local_photos.api.client.PILImage.open", blocked_open)


@pytest.mark.unit
async def test_discovery_lists_albums_without_cataloguing(hass: HomeAssistant, tmp_path: Path) -> None:
    """Discovery reports the album folders and leaves the photos unread."""
    _create_photos(tmp_path / "holiday", 2)
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path)})

    with patch.object(LocalPhotosManager, "_catalog_item") as catalog_item:
        await manager.async_discover_albums()

    catalog_item.assert_not_called()
    assert set(manager.albums) == {"ALL", "holiday"}
    assert not manager.scan_complete
    assert await manager.get_media_items("ALL") == []


@pytest.mark.unit
async def test_discovery_reports_a_missing_directory(hass: HomeAssistant, tmp_path: Path) -> None:
    """A missing photo directory is reported before any scan starts."""
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path / "missing")})

    with pytest.raises(LocalPhotosDirectoryNotFoundError):
        await manager.async_discover_albums()


@pytest.mark.unit
async def test_scan_notifies_listeners_and_counts_only_image_skips(hass: HomeAssistant, tmp_path: Path) -> None:
    """Listeners see the finished catalog; non-image files are not counted as skipped."""
    _create_photos(tmp_path / "holiday", 3)
    (tmp_path / "holiday" / "clip.mp4").write_bytes(b"video")
    (tmp_path / "holiday" / "broken.jpg").write_bytes(b"not a JPEG")
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path), CONF_MAXIMUM_FILE_SIZE: "50"})
    notifications: list[bool] = []
    manager.async_add_listener(lambda: notifications.append(manager.scan_complete))

    await manager.scan_albums()

    assert notifications[-1] is True
    assert manager.albums["ALL"].media_items_count == 3
    assert manager.skipped_count == 1
    assert manager.has_usable_photos(["ALL"])
    assert not manager.has_usable_photos(["holiday"])


@pytest.mark.unit
async def test_catalogued_item_is_not_read_from_disk_again(hass: HomeAssistant, tmp_path: Path) -> None:
    """A catalogued item carries its creation time from the scan's single stat."""
    _create_photos(tmp_path, 1)
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path)})

    with patch.object(MediaItem, "_get_creation_time") as get_creation_time:
        await manager.scan_albums()

    get_creation_time.assert_not_called()
    assert len(await manager.get_media_items("ALL")) == 1


@pytest.mark.unit
async def test_coordinator_shows_a_frame_once_the_background_scan_finds_photos(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """A coordinator starts without photos and renders its first frame as the scan publishes."""
    _create_photos(tmp_path, 3)
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path), CONF_MAXIMUM_FILE_SIZE: "50"})
    await manager.async_discover_albums()
    entry = MockConfigEntry(domain=DOMAIN, title="Test", options={})
    coordinator = LocalPhotosDataUpdateCoordinator(hass, manager, entry, "ALL")
    release_scan = threading.Event()

    with _hold_scan_until(release_scan):
        manager.async_start_scan()
        await coordinator.async_start()

        assert not manager.scan_complete
        assert coordinator.current_media is None

        release_scan.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert manager.scan_complete
    assert coordinator.current_media is not None
    assert coordinator.album is not None
    assert coordinator.album.media_items_count == 3
    assert await coordinator.get_media_data() is not None

    await coordinator.async_shutdown()
    await manager.async_shutdown()


@pytest.mark.unit
async def test_shutdown_stops_a_running_scan(hass: HomeAssistant, tmp_path: Path) -> None:
    """Unloading during a scan stops the worker and publishes nothing further."""
    _create_photos(tmp_path, 3)
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path)})
    await manager.async_discover_albums()
    release_scan = threading.Event()

    with _hold_scan_until(release_scan):
        manager.async_start_scan()
        await manager.async_shutdown()
        release_scan.set()
        await hass.async_block_till_done(wait_background_tasks=True)

    assert not manager.scan_complete
    assert await manager.get_media_items("ALL") == []


@pytest.mark.unit
async def test_multi_picture_jpeg_is_catalogued_and_rendered(hass: HomeAssistant, tmp_path: Path) -> None:
    """A JPEG carrying a multi-picture segment is a normal photo, shown by its main picture."""
    source = tmp_path / "phone.jpg"
    Image.new("RGB", (160, 90), "white").save(
        source, format="MPO", save_all=True, append_images=[Image.new("RGB", (160, 90), "black")]
    )
    manager = LocalPhotosManager(hass, {CONF_FOLDER_PATH: str(tmp_path)})

    await manager.scan_albums()
    items = await manager.get_media_items("ALL")

    assert [item.id for item in items] == ["phone.jpg"]
    assert items[0].dimensions == (160, 90)
    assert manager.skipped_count == 0

    rendered = render_single(items[0].path, 160, 90, crop=True)
    with Image.open(io.BytesIO(rendered)) as image:
        assert image.format == "JPEG"
        assert image.getpixel((80, 45)) == (255, 255, 255)
