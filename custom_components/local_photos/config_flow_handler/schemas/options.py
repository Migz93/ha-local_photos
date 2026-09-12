"""Options flow schemas for local_photos."""

from __future__ import annotations

import voluptuous as vol

from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    CONF_FOLDER_PATH,
    CONF_MAXIMUM_FILE_SIZE,
    SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION,
    SETTING_MAXIMUM_FILE_SIZE_OPTIONS,
)
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv


def get_options_folder_schema(
    current_folder_path: str = "",
    current_maximum_file_size: str = SETTING_MAXIMUM_FILE_SIZE_DEFAULT_OPTION,
) -> vol.Schema:
    """Return the schema for the options folder path step."""
    return vol.Schema(
        {
            vol.Required(CONF_FOLDER_PATH, default=current_folder_path): str,
            vol.Required(CONF_MAXIMUM_FILE_SIZE, default=current_maximum_file_size): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SETTING_MAXIMUM_FILE_SIZE_OPTIONS,
                    translation_key=CONF_MAXIMUM_FILE_SIZE,
                )
            ),
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
