"""Options flow schemas for local_photos."""

from __future__ import annotations

import voluptuous as vol

from custom_components.local_photos.const import CONF_ALBUM_ID, CONF_FOLDER_PATH
import homeassistant.helpers.config_validation as cv


def get_options_folder_schema(current_folder_path: str = "") -> vol.Schema:
    """Return the schema for the options folder path step."""
    return vol.Schema(
        {
            vol.Required(CONF_FOLDER_PATH, default=current_folder_path): str,
        }
    )


def get_options_album_schema(
    album_options: dict[str, str],
    current_albums: list[str] | None = None,
) -> vol.Schema:
    """Return the schema for the options album selection step."""
    return vol.Schema(
        {
            vol.Required(CONF_ALBUM_ID, default=current_albums or ["ALL"]): cv.multi_select(album_options),
        }
    )


__all__ = ["get_options_album_schema", "get_options_folder_schema"]
