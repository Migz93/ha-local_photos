"""Device info utilities for local_photos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.local_photos.const import CONF_ALBUM_ID_FAVORITES, DOMAIN, MANUFACTURER
from homeassistant.helpers.device_registry import DeviceInfo

if TYPE_CHECKING:
    from custom_components.local_photos.api import Album


def create_album_device_info(entry_id: str, album: Album) -> DeviceInfo:
    """Create a DeviceInfo object for a specific album device."""
    if album.id == CONF_ALBUM_ID_FAVORITES:
        device_name = "Local Photos All"
    else:
        device_name = f"Local Photos {album.title}"

    return DeviceInfo(
        identifiers={(DOMAIN, entry_id, album.id)},  # type: ignore[arg-type]
        manufacturer=MANUFACTURER,
        name=device_name,
        configuration_url=None,
    )
