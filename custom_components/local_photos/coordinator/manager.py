"""CoordinatorManager for local_photos.

Manages one LocalPhotosDataUpdateCoordinator instance per album.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from custom_components.local_photos.api import LocalPhotosManager
from custom_components.local_photos.const import CONF_ALBUM_ID

from .base import LocalPhotosDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class CoordinatorManager:
    """Manages all per-album coordinators for a config entry."""

    hass: HomeAssistant
    _config: ConfigEntry
    _photos_manager: LocalPhotosManager | None
    coordinators: dict[str, LocalPhotosDataUpdateCoordinator]
    coordinator_first_refresh: dict[str, asyncio.Task]

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigEntry,
        photos_manager: LocalPhotosManager | None = None,
    ) -> None:
        """Initialize the coordinator manager."""
        self.hass = hass
        self._config = config
        self._photos_manager = photos_manager
        self.coordinators = {}
        self.coordinator_first_refresh = {}

    async def initialize(self) -> None:
        """Initialize the photos manager and coordinators for all configured albums."""
        if self._photos_manager is None:
            self._photos_manager = LocalPhotosManager(self.hass, self._config.options)
            await self._photos_manager.scan_albums()

        album_ids = self._config.options.get(CONF_ALBUM_ID, [])
        for album_id in album_ids:
            await self.get_coordinator(album_id)

    async def get_coordinator(self, album_id: str) -> LocalPhotosDataUpdateCoordinator:
        """Get or create a coordinator for the given album_id."""
        if self._photos_manager is None:
            self._photos_manager = LocalPhotosManager(self.hass, self._config.options)
            await self._photos_manager.scan_albums()

        if album_id in self.coordinators:
            task = self.coordinator_first_refresh.get(album_id)
            if task is not None:
                await task
            return self.coordinators[album_id]

        self.coordinators[album_id] = LocalPhotosDataUpdateCoordinator(
            self.hass, self._photos_manager, self._config, album_id
        )
        first_refresh = asyncio.create_task(self.coordinators[album_id].async_config_entry_first_refresh())
        self.coordinator_first_refresh[album_id] = first_refresh
        await first_refresh
        return self.coordinators[album_id]

    def remove_coordinator(self, album_id: str) -> None:
        """Remove a coordinator instance."""
        self.coordinators.pop(album_id, None)
        self.coordinator_first_refresh.pop(album_id, None)
