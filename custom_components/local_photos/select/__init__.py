"""Select platform for local_photos."""

from __future__ import annotations

from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    PARALLEL_UPDATES as PARALLEL_UPDATES,
    SETTING_ASPECT_RATIO_DEFAULT_OPTION,
    SETTING_ASPECT_RATIO_OPTIONS,
    SETTING_CROP_MODE_DEFAULT_OPTION,
    SETTING_CROP_MODE_OPTIONS,
    SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION,
    SETTING_IMAGESELECTION_MODE_OPTIONS,
    SETTING_INTERVAL_DEFAULT_OPTION,
    SETTING_INTERVAL_OPTIONS,
)
from custom_components.local_photos.coordinator import LocalPhotosDataUpdateCoordinator
from custom_components.local_photos.data import LocalPhotosConfigEntry
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory  # type: ignore[attr-defined]
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Local Photos select entities."""
    coordinator_manager = entry.runtime_data.coordinator_manager

    album_ids = entry.options.get(CONF_ALBUM_ID, [])
    entities = []
    for album_id in album_ids:
        coordinator = await coordinator_manager.get_coordinator(album_id)
        entities.append(LocalPhotosSelectCropMode(coordinator))
        entities.append(LocalPhotosSelectImageSelectionMode(coordinator))
        entities.append(LocalPhotosSelectInterval(coordinator))
        entities.append(LocalPhotosSelectAspectRatio(coordinator))

    async_add_entities(entities, False)


class LocalPhotosSelectCropMode(SelectEntity, RestoreEntity):
    """Select entity for the crop mode setting."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:crop"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the crop mode select."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SelectEntityDescription(
            key="crop_mode",
            name="Crop mode",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_CROP_MODE_OPTIONS,
        )
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-crop-mode"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.coordinator.crop_mode

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option != self.coordinator.crop_mode:
            self.coordinator.set_crop_mode(option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state on add."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_CROP_MODE_OPTIONS:
            self.coordinator.set_crop_mode(SETTING_CROP_MODE_DEFAULT_OPTION)
        else:
            self.coordinator.set_crop_mode(state.state)
        self.async_write_ha_state()


class LocalPhotosSelectImageSelectionMode(SelectEntity, RestoreEntity):
    """Select entity for the image selection mode setting."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:page-next-outline"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the image selection mode select."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SelectEntityDescription(
            key="image_selection_mode",
            name="Image selection mode",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_IMAGESELECTION_MODE_OPTIONS,
        )
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-image-selection-mode"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.coordinator.image_selection_mode

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option != self.coordinator.image_selection_mode:
            self.coordinator.set_image_selection_mode(option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state on add."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_IMAGESELECTION_MODE_OPTIONS:
            self.coordinator.set_image_selection_mode(SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION)
        else:
            self.coordinator.set_image_selection_mode(state.state)
        self.async_write_ha_state()


class LocalPhotosSelectInterval(SelectEntity, RestoreEntity):
    """Select entity for the update interval setting."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-cog"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the update interval select."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SelectEntityDescription(
            key="update_interval",
            name="Update interval",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_INTERVAL_OPTIONS,
        )
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-interval"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.coordinator.interval

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option != self.coordinator.interval:
            self.coordinator.set_interval(option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state on add."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_INTERVAL_OPTIONS:
            self.coordinator.set_interval(SETTING_INTERVAL_DEFAULT_OPTION)
        else:
            self.coordinator.set_interval(state.state)
        self.async_write_ha_state()


class LocalPhotosSelectAspectRatio(SelectEntity, RestoreEntity):
    """Select entity for the aspect ratio setting."""

    coordinator: LocalPhotosDataUpdateCoordinator
    _attr_has_entity_name = True
    _attr_icon = "mdi:aspect-ratio"

    def __init__(self, coordinator: LocalPhotosDataUpdateCoordinator) -> None:
        """Initialize the aspect ratio select."""
        super().__init__()
        self.coordinator = coordinator
        self.entity_description = SelectEntityDescription(
            key="aspect_ratio",
            name="Aspect ratio",
            icon=self._attr_icon,
            entity_category=EntityCategory.CONFIG,
            options=SETTING_ASPECT_RATIO_OPTIONS,
        )
        album_id = self.coordinator.album_id
        self._attr_device_info = self.coordinator.get_device_info()
        self._attr_unique_id = f"{album_id}-aspect-ratio"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.coordinator.aspect_ratio

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option != self.coordinator.aspect_ratio:
            self.coordinator.set_aspect_ratio(option)
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore previous state on add."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state or state.state not in SETTING_ASPECT_RATIO_OPTIONS:
            self.coordinator.set_aspect_ratio(SETTING_ASPECT_RATIO_DEFAULT_OPTION)
        else:
            self.coordinator.set_aspect_ratio(state.state)
        self.async_write_ha_state()
