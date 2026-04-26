"""Coordinator package for local_photos.

- base.py: Per-album DataUpdateCoordinator (LocalPhotosDataUpdateCoordinator)
- manager.py: CoordinatorManager — manages one coordinator per album
- image_processing.py: Pure PIL image processing functions (sync, run in executor)
"""

from __future__ import annotations

from .base import LocalPhotosDataUpdateCoordinator
from .manager import CoordinatorManager

__all__ = ["CoordinatorManager", "LocalPhotosDataUpdateCoordinator"]
