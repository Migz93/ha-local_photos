"""Config flow schemas for local_photos."""

from __future__ import annotations

import voluptuous as vol

from custom_components.local_photos.const import CONF_ALBUM_ID, CONF_FOLDER_PATH


def get_user_schema(suggested_folder_path: str = "") -> vol.Schema:
    """Return the schema for the user (folder path) step."""
    return vol.Schema(
        {
            vol.Required(CONF_FOLDER_PATH, default=suggested_folder_path): str,
        }
    )


def get_album_select_schema(
    album_options: dict[str, str],
    default_album: str = "ALL",
) -> vol.Schema:
    """Return the schema for the album selection step."""
    return vol.Schema(
        {
            vol.Required(CONF_ALBUM_ID, default=default_album): vol.In(album_options),
        }
    )


__all__ = ["get_album_select_schema", "get_user_schema"]
