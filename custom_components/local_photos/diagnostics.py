"""Diagnostics support for local_photos."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_FOLDER_PATH

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import LocalPhotosConfigEntry

# Redact the photos directory path to avoid leaking filesystem layout
TO_REDACT = {CONF_FOLDER_PATH, "folder_path"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: LocalPhotosConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator_manager = entry.runtime_data.coordinator_manager
    integration = entry.runtime_data.integration

    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    device_info = []
    for device in devices:
        entities = er.async_entries_for_device(entity_reg, device.id)
        device_info.append(
            {
                "id": device.id,
                "name": device.name,
                "manufacturer": device.manufacturer,
                "entity_count": len(entities),
            }
        )

    # Per-album coordinator info
    coordinator_info = {}
    for album_id, coordinator in coordinator_manager.coordinators.items():
        coordinator_info[album_id] = {
            "last_update_success": coordinator.last_update_success,
            "current_media": coordinator.current_media_primary.filename if coordinator.current_media_primary else None,
            "media_count": coordinator.album.media_items_count if coordinator.album else 0,
        }

    integration_info = {
        "name": integration.name,
        "version": integration.version,
        "domain": integration.domain,
    }

    entry_info = {
        "entry_id": entry.entry_id,
        "version": entry.version,
        "domain": entry.domain,
        "title": entry.title,
        "state": str(entry.state),
        "options": async_redact_data(entry.options, TO_REDACT),
    }

    return {
        "entry": entry_info,
        "integration": integration_info,
        "coordinators": coordinator_info,
        "devices": device_info,
    }
