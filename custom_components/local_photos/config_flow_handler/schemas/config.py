"""Config flow schemas for local_photos."""

from __future__ import annotations

import voluptuous as vol

from custom_components.local_photos.const import CONF_ALBUM_ID, CONF_FOLDER_PATH
import homeassistant.helpers.config_validation as cv


def get_user_schema(suggested_folder_path: str = "") -> vol.Schema:
    """Return the schema for the user (folder path) step."""
    return vol.Schema(
        {
            vol.Required(CONF_FOLDER_PATH, default=suggested_folder_path): str,
        }
    )


def get_album_select_schema(
    album_options: dict[str, str],
    default_albums: list[str] | None = None,
) -> vol.Schema:
    """Return the schema for the album selection step."""
    return vol.Schema(
        {
            vol.Required(CONF_ALBUM_ID, default=default_albums or ["ALL"]): cv.multi_select(album_options),
        }
    )


__all__ = ["get_album_select_schema", "get_user_schema"]
