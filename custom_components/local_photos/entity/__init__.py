"""
Entity package for local_photos.

Architecture:
    All platform entities inherit from (PlatformEntity, LocalPhotosEntity).
    MRO order matters — platform-specific class first, then the integration base.
    Entities read data from coordinator.data and NEVER call the API client directly.
    Unique IDs follow the pattern: {entry_id}_{description.key}

See entity/base.py for the LocalPhotosEntity base class.
"""

from .base import LocalPhotosEntity

__all__ = ["LocalPhotosEntity"]
