"""Folder path validation for local_photos config flow."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.local_photos.api import LocalPhotosDirectoryNotFoundError


async def validate_folder_path(hass: HomeAssistant, folder_path: str) -> dict[str, str]:
    """Validate a folder path and return a dict of album_id -> display label.

    Normalises relative paths against the HA config directory.

    Raises LocalPhotosDirectoryNotFoundError if the path does not exist.
    """
    p = Path(folder_path)
    if not p.is_absolute():
        p = Path(hass.config.config_dir) / folder_path

    def _scan() -> dict[str, str]:
        if not p.exists():
            raise LocalPhotosDirectoryNotFoundError(f"Directory does not exist: {p}")
        albums: dict[str, str] = {"ALL": "All Photos"}
        for item in p.iterdir():
            if item.is_dir():
                image_count = sum(
                    1 for f in item.rglob("*") if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
                )
                albums[item.name] = f"{item.name} ({image_count} items)"
        return albums

    return await hass.async_add_executor_job(_scan)
