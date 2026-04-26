"""Base entity class for local_photos.

All sensor and camera entities inherit from LocalPhotosEntity for consistent
coordinator integration. Select entities inherit directly from SelectEntity
and RestoreEntity (they don't use the standard EntityDescription pattern).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.local_photos.coordinator import LocalPhotosDataUpdateCoordinator
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription


class LocalPhotosEntity(CoordinatorEntity[LocalPhotosDataUpdateCoordinator]):
    """Base entity class for local_photos.

    Provides coordinator integration and has_entity_name convention.
    Device info and unique_id are set per-entity (not here) because each
    album creates a separate device.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LocalPhotosDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
