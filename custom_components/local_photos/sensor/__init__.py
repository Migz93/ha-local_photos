"""Sensor platform for local_photos."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from custom_components.local_photos.const import CONF_ALBUM_ID, PARALLEL_UPDATES as PARALLEL_UPDATES
from custom_components.local_photos.coordinator import LocalPhotosDataUpdateCoordinator
from custom_components.local_photos.data import LocalPhotosConfigEntry
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Local Photos sensor entities."""
    coordinator_manager = entry.runtime_data.coordinator_manager

    album_ids = entry.options.get(CONF_ALBUM_ID, [])
    entities = []
    for album_id in album_ids:
        coordinator = await coordinator_manager.get_coordinator(album_id)
        entities.append(LocalPhotosMediaCount(coordinator))
        entities.append(LocalPhotosFileName(coordinator))
        entities.append(LocalPhotosCreationTimestamp(coordinator))

    async_add_entities(entities, False)


class LocalPhotosFileName(SensorEntity):
    """Sensor displaying the filename of the current photo."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:text-short"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the filename sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SensorEntityDescription(key="filename", name="Filename", icon=self._attr_icon)
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-filename"

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))
        self._read_value()

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def available(self) -> bool:
        """Available when coordinator has data and a media item is selected."""
        return self.coordinator.last_update_success and self.coordinator.current_media is not None

    def _read_value(self) -> None:
        media = self.coordinator.current_media
        if media is not None:
            secondary_media = self.coordinator.current_secondary_media
            if secondary_media is not None:
                self._attr_native_value = f"{media.filename} & {secondary_media.filename}"
            else:
                self._attr_native_value = media.filename
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._read_value()


class LocalPhotosCreationTimestamp(SensorEntity):
    """Sensor displaying the creation/modification timestamp of the current photo."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the creation timestamp sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SensorEntityDescription(
            key="creation_timestamp",
            name="Creation timestamp",
            icon=self._attr_icon,
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-creation-timestamp"

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))
        self._read_value()

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def available(self) -> bool:
        """Available when coordinator has data and a media item is selected."""
        return self.coordinator.last_update_success and self.coordinator.current_media is not None

    def _read_value(self) -> None:
        val = None
        if self.coordinator.current_media is not None:
            try:
                file_path = self.coordinator.current_media.path
                p = Path(file_path)
                if p.exists():
                    mtime = p.stat().st_mtime
                    val = datetime.datetime.fromtimestamp(mtime, tz=datetime.UTC)
            except Exception as ex:  # noqa: BLE001
                _LOGGER.warning(
                    "Error getting creation time for %s: %s",
                    self.coordinator.current_media.path,
                    ex,
                )
        self._attr_native_value = val
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._read_value()


class LocalPhotosMediaCount(SensorEntity):
    """Sensor displaying the number of photos in the current album."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the media count sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SensorEntityDescription(key="media_count", name="Media count", icon=self._attr_icon)
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-mediacount"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def available(self) -> bool:
        """Available when coordinator has data."""
        return self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.album is not None:
            self._attr_native_value = self.coordinator.album.media_items_count
            self._attr_extra_state_attributes = {
                "album_id": self.coordinator.album.id,
                "album_title": self.coordinator.album.title,
            }
        self.async_write_ha_state()
