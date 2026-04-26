"""Custom types for local_photos.

Defines the runtime data structure attached to each config entry.
Access pattern: entry.runtime_data.manager / entry.runtime_data.coordinator_manager
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import LocalPhotosManager
    from .coordinator import CoordinatorManager


type LocalPhotosConfigEntry = ConfigEntry[LocalPhotosData]


@dataclass
class LocalPhotosData:
    """Runtime data for local_photos config entries.

    Stored as entry.runtime_data after successful setup.
    """

    manager: LocalPhotosManager
    coordinator_manager: CoordinatorManager
    integration: Integration
