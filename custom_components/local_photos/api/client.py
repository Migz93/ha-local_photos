"""Filesystem manager for local_photos.

Provides LocalPhotosManager, Album, and MediaItem classes for scanning and
accessing local photo directories. All filesystem operations that may block
should be called via hass.async_add_executor_job.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import logging
import mimetypes
from pathlib import Path
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.local_photos.const import CONF_ALBUM_ID_FAVORITES, CONF_FOLDER_PATH

_LOGGER = logging.getLogger(__name__)

# Supported image file extensions — always available via Pillow
SUPPORTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"]

# Optional HEIC/HEIF support (requires pillow-heif and libheif system library)
try:
    from pillow_heif import register_heif_opener  # type: ignore[import-untyped]

    register_heif_opener()
    SUPPORTED_EXTENSIONS.extend([".heic", ".heif"])
    mimetypes.add_type("image/heic", ".heic")
    mimetypes.add_type("image/heif", ".heif")
    _LOGGER.debug("HEIC/HEIF support enabled via pillow-heif")
except ImportError:
    _LOGGER.debug("pillow-heif not available; HEIC/HEIF files will be skipped")

# Optional AVIF support (requires pillow-avif-plugin or Pillow compiled with libavif)
try:
    import pillow_avif  # type: ignore[import-untyped] # noqa: F401

    SUPPORTED_EXTENSIONS.append(".avif")
    mimetypes.add_type("image/avif", ".avif")
    _LOGGER.debug("AVIF support enabled via pillow-avif-plugin")
except ImportError:
    _LOGGER.debug("pillow-avif-plugin not available; AVIF files will be skipped")


class LocalPhotosFilesystemError(Exception):
    """Base exception for filesystem errors."""


class LocalPhotosDirectoryNotFoundError(LocalPhotosFilesystemError):
    """Exception raised when the photos directory does not exist."""


class LocalPhotosPermissionError(LocalPhotosFilesystemError):
    """Exception raised when access to the photos directory is denied."""


class Album:
    """Representation of a local photo album (folder)."""

    def __init__(self, id: str, title: str, path: str) -> None:
        """Initialize a local album."""
        self.id = id
        self.title = title
        self.path = path
        self.is_writeable = False
        self.media_items_count = 0
        self.product_url = None

    def get(self, key: str, default: object = None) -> object:
        """Get album attribute."""
        if key == "id":
            return self.id
        if key == "title":
            return self.title
        if key == "isWriteable":
            return self.is_writeable
        if key == "mediaItemsCount":
            return self.media_items_count
        if key == "productUrl":
            return self.product_url
        return default


class MediaItem:
    """Representation of a local media item (photo)."""

    def __init__(self, id: str, filename: str, path: str) -> None:
        """Initialize a local media item."""
        self.id = id
        self.filename = filename
        self.path = path
        self.creation_time = self._get_creation_time()
        self.media_metadata = self._get_media_metadata()
        self.product_url = None
        self.contributor_info = None

    def _get_creation_time(self) -> datetime:
        """Get creation time from file metadata."""
        try:
            stat = Path(self.path).stat()
            ctime = datetime.fromtimestamp(stat.st_ctime)
            mtime = datetime.fromtimestamp(stat.st_mtime)
            return min(ctime, mtime)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("Error getting creation time for %s: %s", self.path, ex)
            return datetime.now()

    def _get_media_metadata(self) -> dict:
        """Get basic media metadata."""
        return {
            "photo": {
                "cameraMake": "Local Photos",
                "cameraModel": "File System",
            },
            "creationTime": self.creation_time.isoformat(),
        }

    def get(self, key: str, default: object = None) -> object:
        """Get media item attribute."""
        if key == "id":
            return self.id
        if key == "filename":
            return self.filename
        if key == "mediaMetadata":
            return self.media_metadata
        if key == "productUrl":
            return self.product_url
        if key == "contributorInfo":
            return self.contributor_info
        return default


class LocalPhotosManager:
    """Manager for local photos — the filesystem abstraction layer."""

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        """Initialize the local photos manager."""
        self.hass = hass
        self.config = config

        folder_path = config.get(CONF_FOLDER_PATH)
        if folder_path:
            p = Path(folder_path)
            if not p.is_absolute():
                p = Path(hass.config.config_dir) / folder_path
            self.photos_dir = str(p)
        else:
            self.photos_dir = str(Path(hass.config.config_dir) / "www" / "photos")

        self.albums: dict[str, Album] = {}

    async def scan_albums(self) -> None:
        """Scan for local photo albums (folders).

        Raises LocalPhotosDirectoryNotFoundError if the photos directory does not exist.
        """
        dir_exists = await self.hass.async_add_executor_job(Path(self.photos_dir).exists)
        if not dir_exists:
            _LOGGER.error("Photos directory does not exist: %s", self.photos_dir)
            raise LocalPhotosDirectoryNotFoundError(f"Directory does not exist: {self.photos_dir}")

        all_album_id = self.config.get(CONF_ALBUM_ID_FAVORITES, "ALL")
        all_album = Album(id=all_album_id, title="All", path=self.photos_dir)
        self.albums[all_album.id] = all_album

        try:
            photos_path = Path(self.photos_dir)
            dir_items = await self.hass.async_add_executor_job(lambda: list(photos_path.iterdir()))
            for item_path in dir_items:
                is_dir = await self.hass.async_add_executor_job(item_path.is_dir)
                if is_dir:
                    album = Album(id=item_path.name, title=item_path.name, path=str(item_path))
                    self.albums[album.id] = album
                    _LOGGER.debug("Found album: %s at %s", album.title, album.path)
        except PermissionError as ex:
            raise LocalPhotosPermissionError(f"Permission denied scanning {self.photos_dir}") from ex
        except OSError as ex:
            _LOGGER.error("Error scanning for albums: %s", ex)

    def get_albums(self) -> list[Album]:
        """Get all available albums."""
        return list(self.albums.values())

    def get_album(self, album_id: str) -> Album | None:
        """Get album by ID."""
        return self.albums.get(album_id)

    async def get_media_items(self, album_id: str) -> list[MediaItem]:
        """Get all media items in an album, sorted alphabetically."""
        album = self.get_album(album_id)
        if not album:
            _LOGGER.error("Album not found: %s", album_id)
            return []

        media_items: list[MediaItem] = []
        all_album_id = self.config.get(CONF_ALBUM_ID_FAVORITES, "ALL")

        if album_id == all_album_id:

            def walk_directory() -> list[tuple[str, str]]:
                result = []
                for root, _, files in Path(album.path).walk():  # type: ignore[attr-defined]
                    for file in files:
                        file_path = root / file
                        result.append((file, str(file_path)))
                return result

            file_paths = await self.hass.async_add_executor_job(walk_directory)
            for file, file_path in file_paths:
                is_valid = await self.hass.async_add_executor_job(self._is_valid_image, file_path)
                if is_valid:
                    media_items.append(MediaItem(id=file, filename=file, path=file_path))
        else:
            try:
                album_path = Path(album.path)
                dir_files = await self.hass.async_add_executor_job(list, album_path.iterdir())
                for item in dir_files:
                    is_file = await self.hass.async_add_executor_job(item.is_file)
                    if is_file:
                        is_valid = await self.hass.async_add_executor_job(self._is_valid_image, str(item))
                        if is_valid:
                            media_items.append(MediaItem(id=item.name, filename=item.name, path=str(item)))
            except OSError as ex:
                _LOGGER.error("Error getting media items for album %s: %s", album_id, ex)

        album.media_items_count = len(media_items)
        media_items.sort(key=lambda item: item.filename.lower())
        return media_items

    async def get_media_item(self, album_id: str, media_id: str) -> MediaItem | None:
        """Get a specific media item by ID."""
        media_items = await self.get_media_items(album_id)
        for item in media_items:
            if item.id == media_id:
                return item
        return None

    async def get_random_media_item(self, album_id: str) -> MediaItem | None:
        """Get a random media item from an album."""
        media_items = await self.get_media_items(album_id)
        if not media_items:
            return None
        return random.choice(media_items)

    async def get_next_media_item(self, album_id: str, current_media_id: str | None) -> MediaItem | None:
        """Get the next media item in alphabetical order."""
        media_items = await self.get_media_items(album_id)
        if not media_items:
            return None
        if not current_media_id:
            return media_items[0]
        current_index = next(
            (i for i, item in enumerate(media_items) if item.id == current_media_id),
            -1,
        )
        if current_index >= 0:
            return media_items[(current_index + 1) % len(media_items)]
        return media_items[0]

    def _is_valid_image(self, file_path: str) -> bool:
        """Check if a file is a valid image (synchronous, run in executor)."""
        p = Path(file_path)
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        try:
            if not p.is_file():
                return False
            file_size = p.stat().st_size
            if file_size > 20 * 1024 * 1024:
                _LOGGER.warning("File too large (>20MB): %s", file_path)
                return False
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type or not mime_type.startswith("image/"):
                return False
        except OSError as ex:
            _LOGGER.error("Error checking image file %s: %s", file_path, ex)
            return False
        else:
            return True
