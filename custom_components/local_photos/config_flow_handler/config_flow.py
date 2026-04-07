"""Config flow for local_photos."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from custom_components.local_photos.api import LocalPhotosDirectoryNotFoundError
from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_ID_FAVORITES,
    CONF_FOLDER_PATH,
    CONF_WRITEMETADATA,
    DOMAIN,
)
from homeassistant import config_entries

from .schemas import get_album_select_schema, get_user_schema
from .validators import validate_folder_path

if TYPE_CHECKING:
    from .options_flow import LocalPhotosOptionsFlow


class LocalPhotosConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for local_photos."""

    VERSION = 2

    folder_path: str

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> LocalPhotosOptionsFlow:
        """Get the options flow for this handler."""
        from .options_flow import LocalPhotosOptionsFlow  # noqa: PLC0415

        return LocalPhotosOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the folder path step."""
        errors: dict[str, str] = {}
        default_path = str(Path(self.hass.config.config_dir) / "www" / "images")

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

        return self.async_show_form(
            step_id="user",
            data_schema=get_user_schema(
                suggested_folder_path=user_input.get(CONF_FOLDER_PATH, default_path) if user_input else default_path
            ),
            errors=errors,
        )

    async def async_step_album_select(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the album selection step."""
        if user_input is None:
            album_options = await validate_folder_path(self.hass, self.folder_path)
            return self.async_show_form(
                step_id="album_select",
                data_schema=get_album_select_schema(album_options),
            )

        album_id = user_input[CONF_ALBUM_ID]

        # Check for duplicate entry
        for entry in self._async_current_entries():
            if entry.options.get(CONF_ALBUM_ID, []) == [album_id]:
                return self.async_abort(reason="already_configured")

        title = "Local Photos All" if album_id == CONF_ALBUM_ID_FAVORITES else f"Local Photos {album_id}"
        options = {
            CONF_ALBUM_ID: [album_id],
            CONF_FOLDER_PATH: self.folder_path,
            CONF_WRITEMETADATA: True,
        }
        return self.async_create_entry(title=title, data={}, options=options)


__all__ = ["LocalPhotosConfigFlowHandler"]
