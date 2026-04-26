"""Options flow for local_photos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from custom_components.local_photos.api import LocalPhotosDirectoryNotFoundError
from custom_components.local_photos.const import CONF_ALBUM_ID, CONF_ALBUM_ID_FAVORITES, CONF_FOLDER_PATH
from homeassistant import config_entries

from .schemas import get_options_album_schema, get_options_folder_schema
from .validators import validate_folder_path


class LocalPhotosOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for local_photos."""

    folder_path: str

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the folder path options step."""
        errors: dict[str, str] = {}
        current_folder_path = self.config_entry.options.get(
            CONF_FOLDER_PATH,
            str(Path(self.hass.config.config_dir) / "www" / "images"),
        )

        if user_input is not None:
            folder_path = user_input[CONF_FOLDER_PATH]
            p = Path(folder_path)
            if not p.is_absolute():
                folder_path = str(Path(self.hass.config.config_dir) / folder_path)
            try:
                await validate_folder_path(self.hass, folder_path)
                self.folder_path = folder_path
                return await self.async_step_album_select()
            except LocalPhotosDirectoryNotFoundError:
                errors["base"] = "directory_not_found"
                current_folder_path = user_input[CONF_FOLDER_PATH]

        return self.async_show_form(
            step_id="init",
            data_schema=get_options_folder_schema(current_folder_path),
            errors=errors,
        )

    async def async_step_album_select(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the album selection options step."""
        if user_input is None:
            album_options = await validate_folder_path(self.hass, self.folder_path)
            current_album_ids = self.config_entry.options.get(CONF_ALBUM_ID, [CONF_ALBUM_ID_FAVORITES])
            current_album = (
                current_album_ids[0]
                if isinstance(current_album_ids, list) and current_album_ids
                else CONF_ALBUM_ID_FAVORITES
            )
            return self.async_show_form(
                step_id="album_select",
                data_schema=get_options_album_schema(album_options, current_album),
            )

        album_id = user_input[CONF_ALBUM_ID]
        updated_options = {
            **self.config_entry.options,
            CONF_ALBUM_ID: [album_id],
            CONF_FOLDER_PATH: self.folder_path,
        }
        return self.async_create_entry(title="", data=updated_options)


__all__ = ["LocalPhotosOptionsFlow"]
