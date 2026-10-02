"""Filesystem catalog for local_photos.

The catalog contains source metadata only. Rendering is deliberately owned by
the coordinator, so serving a camera image never requires walking the photo
library again. The catalog fills in the background after setup, so a large or
slow library cannot hold up Home Assistant.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime
import logging
import os
from pathlib import Path
import random
import threading
import time
from typing import TYPE_CHECKING, Any

from PIL import Image as PILImage, UnidentifiedImageError

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_ID_FAVORITES,
    CONF_FOLDER_PATH,
    CONF_MAXIMUM_FILE_SIZE,
    MAX_SOURCE_PIXELS,
    SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION,
)

_LOGGER = logging.getLogger(__name__)

# Register optional codecs before asking Pillow which extensions it can decode.
try:
    from pillow_heif import register_heif_opener  # type: ignore[import-untyped]

    register_heif_opener(thumbnails=True, decode_threads=1)
except ImportError:
    _LOGGER.debug("pillow-heif is unavailable; HEIC/HEIF files are not supported")

try:
    import pillow_avif  # type: ignore[import-untyped] # noqa: F401
except ImportError:
    _LOGGER.debug("pillow-avif-plugin is unavailable; AVIF files are not supported")

_PHOTO_FORMATS = frozenset({"AVIF", "BMP", "GIF", "HEIF", "JPEG", "PNG", "TIFF", "WEBP"})
SUPPORTED_EXTENSIONS = frozenset(
    extension.lower()
    for extension, image_format in PILImage.registered_extensions().items()
    if image_format in _PHOTO_FORMATS
)

_FIRST_PUBLISH_COUNT = 10
_PUBLISH_INTERVAL_SECONDS = 5.0
_PROGRESS_LOG_INTERVAL_SECONDS = 30.0


class LocalPhotosFilesystemError(Exception):
    """Base exception for filesystem errors."""


class LocalPhotosDirectoryNotFoundError(LocalPhotosFilesystemError):
    """Raised when the photos directory does not exist."""


class LocalPhotosPermissionError(LocalPhotosFilesystemError):
    """Raised when access to the photos directory is denied."""


class Album:
    """Representation of a local photo album (folder)."""

    def __init__(self, id: str, title: str, path: str) -> None:
        """Initialize an album record."""
        self.id = id
        self.title = title
        self.path = path
        self.is_writeable = False
        self.media_items_count = 0
        self.product_url = None

    def get(self, key: str, default: object = None) -> object:
        """Get album attribute."""
        return {
            "id": self.id,
            "title": self.title,
            "isWriteable": self.is_writeable,
            "mediaItemsCount": self.media_items_count,
            "productUrl": self.product_url,
        }.get(key, default)


class MediaItem:
    """Metadata for a single catalogued source image."""

    def __init__(
        self,
        id: str,
        filename: str,
        path: str,
        *,
        fingerprint: str | None = None,
        dimensions: tuple[int, int] | None = None,
        creation_time: datetime | None = None,
    ) -> None:
        """Initialize immutable-in-practice source metadata."""
        self.id = id
        self.filename = filename
        self.path = path
        self.fingerprint = fingerprint or path
        self.dimensions = dimensions
        self.creation_time = creation_time or self._get_creation_time()
        self.media_metadata = {
            "photo": {"cameraMake": "Local Photos", "cameraModel": "File System"},
            "creationTime": self.creation_time.isoformat(),
        }
        self.product_url = None
        self.contributor_info = None

    def _get_creation_time(self) -> datetime:
        try:
            stat = Path(self.path).stat()
            return datetime.fromtimestamp(min(stat.st_ctime, stat.st_mtime))
        except OSError as err:
            _LOGGER.debug("Could not read creation time for %s: %s", self.path, err)
            return datetime.now()

    def get(self, key: str, default: object = None) -> object:
        """Get media item attribute."""
        return {
            "id": self.id,
            "filename": self.filename,
            "mediaMetadata": self.media_metadata,
            "productUrl": self.product_url,
            "contributorInfo": self.contributor_info,
        }.get(key, default)


class LocalPhotosManager:
    """Catalog local photos for all configured albums."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        """Initialize a catalog using the config entry's options."""
        self.hass = hass
        self.config = config
        configured_path = config.get(CONF_FOLDER_PATH)
        photos_path = Path(configured_path) if configured_path else Path(hass.config.config_dir) / "www" / "photos"
        if not photos_path.is_absolute():
            photos_path = Path(hass.config.config_dir) / photos_path
        self.photos_dir = str(photos_path)
        self.albums: dict[str, Album] = {}
        self._merged_sources: dict[str, list[str]] = {}
        self._media_by_album: dict[str, list[MediaItem]] = {}
        self.skipped_count = 0
        self.scan_complete = False
        self._all_id: str = CONF_ALBUM_ID_FAVORITES
        self._scan_all = False
        self._selected_paths: dict[str, Path] = {}
        self._listeners: list[Callable[[], None]] = []
        self._scan_stop: threading.Event | None = None
        self._scan_task: asyncio.Task[None] | None = None
        configured_size = config.get(CONF_MAXIMUM_FILE_SIZE, SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION)
        try:
            self.maximum_file_size_bytes = int(configured_size) * 1024 * 1024
        except TypeError, ValueError:
            self.maximum_file_size_bytes = int(SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION) * 1024 * 1024

    async def async_discover_albums(self) -> None:
        """Verify the photo directory and list its albums without reading photos."""
        photos_path = Path(self.photos_dir)

        def discover() -> dict[str, Path]:
            if not photos_path.exists() or not photos_path.is_dir():
                raise LocalPhotosDirectoryNotFoundError(f"Directory does not exist: {self.photos_dir}")
            # Discover direct child folders only. This must stay cheap: a root
            # can itself be a large network photo library.
            return {path.name: path for path in photos_path.iterdir() if path.is_dir()}

        try:
            child_albums = await self.hass.async_add_executor_job(discover)
        except PermissionError as err:
            raise LocalPhotosPermissionError(f"Permission denied scanning {self.photos_dir}") from err

        all_id = self.config.get(CONF_ALBUM_ID_FAVORITES, "ALL")
        self.albums = {all_id: Album(id=all_id, title="All", path=str(photos_path))}
        self._media_by_album = {all_id: []}
        for album_id, album_path in child_albums.items():
            self.albums[album_id] = Album(id=album_id, title=album_id, path=str(album_path))
            self._media_by_album[album_id] = []

        selected = self.config.get(CONF_ALBUM_ID, [all_id])
        selected_ids = set(selected) if isinstance(selected, list) else {all_id}
        self._all_id = all_id
        self._scan_all = all_id in selected_ids
        self._selected_paths = {
            album_id: child_albums[album_id] for album_id in selected_ids if album_id in child_albums
        }
        self.skipped_count = 0
        self.scan_complete = False

    def async_start_scan(self) -> None:
        """Start cataloguing the selected albums in the background."""
        self._scan_stop = threading.Event()
        self._scan_task = self.hass.async_create_background_task(
            self._async_run_scan(self._scan_stop), name=f"local_photos catalog scan {self.photos_dir}"
        )

    async def scan_albums(self) -> None:
        """Discover the albums and wait for the whole catalog to be built."""
        await self.async_discover_albums()
        self._scan_stop = threading.Event()
        await self._async_run_scan(self._scan_stop)

    async def async_shutdown(self) -> None:
        """Stop a running scan; its worker thread exits at the next file."""
        if self._scan_stop is not None:
            self._scan_stop.set()
        if self._scan_task is not None:
            self._scan_task.cancel()
            await asyncio.gather(self._scan_task, return_exceptions=True)
            self._scan_task = None
        self._listeners.clear()

    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` whenever catalogued items or scan state change."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def has_usable_photos(self, album_ids: list[str]) -> bool:
        """Return whether any of the given albums has a catalogued photo."""
        return any(self._media_by_album.get(album_id) for album_id in album_ids)

    async def _async_run_scan(self, stop: threading.Event) -> None:
        try:
            final_batch, final_skipped = await self.hass.async_add_executor_job(self._scan, stop)
        except asyncio.CancelledError:
            stop.set()
            raise
        except OSError as err:
            _LOGGER.warning("Photo scan of %s stopped early: %s", self.photos_dir, err)
        else:
            self._async_publish(stop, final_batch, final_skipped)
        for media in self._media_by_album.values():
            media.sort(key=lambda item: item.filename.lower())
        self.scan_complete = True
        self._async_notify_listeners()

    def _scan(self, stop: threading.Event) -> tuple[list[tuple[MediaItem, str | None]], int]:
        """Walk the selected albums in a worker thread, publishing items in batches.

        Returns the last, not yet published batch and its skipped-file count.
        """
        photos_path = Path(self.photos_dir)
        if self._scan_all:
            # "All Photos" intentionally remains an explicit full-tree scan.
            # Populate selected child albums from this one walk too.
            roots: list[tuple[Path, str | None]] = [(photos_path, None)]
        else:
            # A merged entry scans only its selected top-level folders;
            # unselected siblings are never enumerated or opened.
            roots = [(album_path, album_id) for album_id, album_path in self._selected_paths.items()]

        batch: list[tuple[MediaItem, str | None]] = []
        catalogued = skipped = unpublished_skipped = 0
        started = last_publish = last_log = time.monotonic()

        def publish() -> None:
            nonlocal batch, unpublished_skipped, last_publish
            if batch or unpublished_skipped:
                self.hass.loop.call_soon_threadsafe(self._async_publish, stop, batch, unpublished_skipped)
            batch = []
            unpublished_skipped = 0
            last_publish = time.monotonic()

        def unreadable_folder(err: OSError) -> None:
            _LOGGER.warning("Could not read photo folder %s: %s", err.filename, err)

        _LOGGER.info("Scanning %s for photos", self.photos_dir)
        for root, root_album_id in roots:
            for folder, subfolders, filenames in os.walk(root, onerror=unreadable_folder):
                subfolders.sort()
                for filename in filenames:
                    if stop.is_set():
                        return [], 0
                    path = Path(folder, filename)
                    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    item = self._catalog_item(photos_path, path)
                    if item is None:
                        skipped += 1
                        unpublished_skipped += 1
                    else:
                        album_id = root_album_id
                        if album_id is None:
                            top_folder = item.id.split("/", 1)[0]
                            album_id = top_folder if top_folder in self._selected_paths else None
                        batch.append((item, album_id))
                        catalogued += 1
                    now = time.monotonic()
                    if now - last_publish >= _PUBLISH_INTERVAL_SECONDS or catalogued == _FIRST_PUBLISH_COUNT:
                        publish()
                    if now - last_log >= _PROGRESS_LOG_INTERVAL_SECONDS:
                        last_log = now
                        _LOGGER.info(
                            "Still scanning %s: %d photos catalogued, %d skipped so far",
                            self.photos_dir,
                            catalogued,
                            skipped,
                        )
        _LOGGER.info(
            "Catalogued %d photos from %s in %.0f seconds (%d skipped)",
            catalogued,
            self.photos_dir,
            time.monotonic() - started,
            skipped,
        )
        return batch, unpublished_skipped

    def _async_publish(self, stop: threading.Event, batch: list[tuple[MediaItem, str | None]], skipped: int) -> None:
        """Add a scanned batch to the catalog from the event loop."""
        if stop.is_set():
            return
        for item, album_id in batch:
            if self._scan_all:
                self._media_by_album[self._all_id].append(item)
            if album_id is not None:
                self._media_by_album[album_id].append(item)
        self.skipped_count += skipped
        self._async_notify_listeners()

    def _async_notify_listeners(self) -> None:
        for album_id, media in self._media_by_album.items():
            self.albums[album_id].media_items_count = len(media)
        for merged_id, source_ids in self._merged_sources.items():
            self.albums[merged_id].media_items_count = len(
                {item.path for source_id in source_ids for item in self._media_by_album.get(source_id, [])}
            )
        for listener in list(self._listeners):
            listener()

    def _catalog_item(self, root: Path, path: Path) -> MediaItem | None:
        """Return header-validated metadata, logging skips only at debug level."""
        try:
            stat = path.stat()
            if stat.st_size > self.maximum_file_size_bytes:
                _LOGGER.debug(
                    "Skipping %s: exceeds the configured %s MiB limit", path, self.maximum_file_size_bytes // 2**20
                )
                return None
            with PILImage.open(path) as image:
                if image.format not in _PHOTO_FORMATS:
                    _LOGGER.debug("Skipping %s: unsupported decoded format %s", path, image.format)
                    return None
                width, height = image.size
                if width * height > MAX_SOURCE_PIXELS:
                    _LOGGER.debug("Skipping %s: source exceeds the internal pixel safety limit", path)
                    return None
                orientation = image.getexif().get(0x0112, 1)
                if orientation in (5, 6, 7, 8):
                    width, height = height, width
        except (OSError, UnidentifiedImageError, ValueError) as err:
            _LOGGER.debug("Skipping unreadable image %s: %s", path, err)
            return None
        relative_path = path.relative_to(root).as_posix()
        return MediaItem(
            id=relative_path,
            filename=path.name,
            path=str(path),
            fingerprint=f"{relative_path}:{stat.st_size}:{stat.st_mtime_ns}",
            dimensions=(width, height),
            creation_time=datetime.fromtimestamp(min(stat.st_ctime, stat.st_mtime)),
        )

    def register_merged_album(self, source_album_ids: list[str], merged_id: str, title: str) -> None:
        """Register a virtual album composed from several catalog albums."""
        self._merged_sources[merged_id] = source_album_ids
        self.albums[merged_id] = Album(id=merged_id, title=title, path="")

    def get_albums(self) -> list[Album]:
        """Return catalogued albums."""
        return list(self.albums.values())

    def get_album(self, album_id: str) -> Album | None:
        """Return one catalogued album."""
        return self.albums.get(album_id)

    async def get_media_items(self, album_id: str) -> list[MediaItem]:
        """Return catalogued items without filesystem work."""
        if album_id in self._merged_sources:
            seen: set[str] = set()
            items: list[MediaItem] = []
            for source_id in self._merged_sources[album_id]:
                for item in self._media_by_album.get(source_id, []):
                    if item.path not in seen:
                        seen.add(item.path)
                        items.append(item)
            items.sort(key=lambda item: item.filename.lower())
            self.albums[album_id].media_items_count = len(items)
            return items
        return list(self._media_by_album.get(album_id, []))

    async def get_media_item(self, album_id: str, media_id: str) -> MediaItem | None:
        """Return a catalogued item by stable relative-path ID."""
        return next((item for item in await self.get_media_items(album_id) if item.id == media_id), None)

    async def get_random_media_item(self, album_id: str, exclude_id: str | None = None) -> MediaItem | None:
        """Return a random catalogued item, optionally excluding one ID."""
        items = [item for item in await self.get_media_items(album_id) if item.id != exclude_id]
        return random.choice(items) if items else None

    async def get_next_media_item(self, album_id: str, current_media_id: str | None) -> MediaItem | None:
        """Return the alphabetically next catalogued item."""
        items = await self.get_media_items(album_id)
        if not items:
            return None
        current_index = next((index for index, item in enumerate(items) if item.id == current_media_id), -1)
        return items[(current_index + 1) % len(items)]


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "Album",
    "LocalPhotosDirectoryNotFoundError",
    "LocalPhotosFilesystemError",
    "LocalPhotosManager",
    "LocalPhotosPermissionError",
    "MediaItem",
]
