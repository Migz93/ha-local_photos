"""
Filesystem abstraction layer for local_photos.

Architecture:
    Three-layer data flow: Entities → Coordinator → Filesystem Manager.
    Only the coordinator should call LocalPhotosManager. Entities must never
    import or call the filesystem layer directly.

Exception hierarchy:
    LocalPhotosFilesystemError (base)
    ├── LocalPhotosDirectoryNotFoundError (path does not exist)
    └── LocalPhotosPermissionError (access denied)

Coordinator exception mapping:
    LocalPhotosDirectoryNotFoundError → ConfigEntryNotReady (retried on next HA start)
    LocalPhotosFilesystemError        → UpdateFailed (auto-retry)
"""

from .client import (
    Album,
    LocalPhotosDirectoryNotFoundError,
    LocalPhotosFilesystemError,
    LocalPhotosManager,
    LocalPhotosPermissionError,
    MediaItem,
)

__all__ = [
    "Album",
    "LocalPhotosDirectoryNotFoundError",
    "LocalPhotosFilesystemError",
    "LocalPhotosManager",
    "LocalPhotosPermissionError",
    "MediaItem",
]
