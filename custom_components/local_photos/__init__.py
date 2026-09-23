"""Custom integration to integrate local_photos with Home Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.loader import async_get_loaded_integration

from .api import LocalPhotosDirectoryNotFoundError, LocalPhotosManager
from .const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_ID_FAVORITES,
    CONF_MAXIMUM_FILE_SIZE,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    LOGGER,
    SETTING_MAXIMUM_FILE_SIZE_20,
    SETTING_MAXIMUM_FILE_SIZE_50,
    SETTING_MAXIMUM_FILE_SIZE_100,
    SETTING_MAXIMUM_FILE_SIZE_200,
    SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION,
)
from .coordinator import CoordinatorManager
from .data import LocalPhotosData
from .repairs import async_update_no_usable_photos_issue
from .service_actions import async_setup_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .data import LocalPhotosConfigEntry

PLATFORMS: list[Platform] = [Platform.CAMERA, Platform.SENSOR, Platform.SELECT]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration — register domain-level services."""
    await async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
) -> bool:
    """Set up local_photos from a config entry."""
    manager = LocalPhotosManager(hass, entry.options)

    try:
        await manager.scan_albums()
    except LocalPhotosDirectoryNotFoundError as err:
        raise ConfigEntryNotReady(str(err)) from err

    selected_albums = entry.options.get(CONF_ALBUM_ID, [CONF_ALBUM_ID_FAVORITES])
    has_usable_photos = False
    for album_id in selected_albums:
        if await manager.get_media_items(album_id):
            has_usable_photos = True
            break
    async_update_no_usable_photos_issue(hass, entry.entry_id, has_usable_photos)

    coordinator_manager = CoordinatorManager(hass, entry, manager)
    await coordinator_manager.initialize()

    entry.runtime_data = LocalPhotosData(
        manager=manager,
        coordinator_manager=coordinator_manager,
        integration=async_get_loaded_integration(hass, entry.domain),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.coordinator_manager.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> bool:
    """Migrate old entries and raise the minimum source-size guard."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        return False

    LOGGER.debug("Migrating from version %s", config_entry.version)

    options = dict(config_entry.options)
    configured_limit = str(options.get(CONF_MAXIMUM_FILE_SIZE, SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION))
    if CONF_MAXIMUM_FILE_SIZE not in options or configured_limit == SETTING_MAXIMUM_FILE_SIZE_20:
        options[CONF_MAXIMUM_FILE_SIZE] = SETTING_MAXIMUM_FILE_SIZE_50
    elif configured_limit not in {
        SETTING_MAXIMUM_FILE_SIZE_50,
        SETTING_MAXIMUM_FILE_SIZE_100,
        SETTING_MAXIMUM_FILE_SIZE_200,
    }:
        options[CONF_MAXIMUM_FILE_SIZE] = SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION

    if (
        config_entry.version != CONFIG_ENTRY_VERSION
        or config_entry.minor_version < CONFIG_ENTRY_MINOR_VERSION
        or options != config_entry.options
    ):
        hass.config_entries.async_update_entry(
            config_entry,
            options=options,
            version=CONFIG_ENTRY_VERSION,
            minor_version=CONFIG_ENTRY_MINOR_VERSION,
        )
        LOGGER.info("Migrated Local Photos entry source-size limit")

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: LocalPhotosConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Remove an album device from the config entry."""
    identifier = next((ident for ident in device_entry.identifiers if ident[0] == DOMAIN), None)
    if identifier is None:
        return False

    coordinator_manager = config_entry.runtime_data.coordinator_manager
    album_id = identifier[-1]

    options = config_entry.options.copy()
    albums = options.get(CONF_ALBUM_ID, []).copy()
    if album_id in albums:
        albums.remove(album_id)
        options[CONF_ALBUM_ID] = albums
        hass.config_entries.async_update_entry(config_entry, options=options)

    coordinator_manager.remove_coordinator(album_id)
    return True
