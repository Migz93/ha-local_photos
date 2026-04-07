"""Service actions package for local_photos.

The next_media service is registered as an entity service on the camera platform
(in camera/__init__.py) rather than here, because it targets specific camera
entities and uses HA's built-in entity targeting.

This module exists to satisfy the Silver Quality Scale requirement of calling
async_setup_services from async_setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up domain-level services.

    Note: next_media is an entity service registered in camera/__init__.py.
    """
