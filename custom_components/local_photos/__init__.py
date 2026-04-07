"""Custom integration to integrate local_photos with Home Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.loader import async_get_loaded_integration

from .api import LocalPhotosDirectoryNotFoundError, LocalPhotosManager
from .const import CONF_ALBUM_ID, DOMAIN, LOGGER
from .coordinator import CoordinatorManager
from .data import LocalPhotosData
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
    """Migrate config entry from v1 to v2.

    v1 → v2: No data format change (everything was already in options).
    Just bump the version number.
    """
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        hass.config_entries.async_update_entry(config_entry, version=2)
        LOGGER.info("Migration to version 2 successful")

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
