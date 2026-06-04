"""Config flow for local_photos."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from custom_components.local_photos.api import LocalPhotosDirectoryNotFoundError
from custom_components.local_photos.const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_ID_FAVORITES,
    CONF_FOLDER_PATH,
    CONF_UNIQUE_ID_PREFIX,
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
    _album_options: dict[str, str]

    def _album_path(self, folder_path: str, album_id: str) -> str:
        """Return the canonical filesystem path represented by an album selection."""
        path = Path(folder_path)
        if not path.is_absolute():
            path = Path(self.hass.config.config_dir) / path
        if album_id != CONF_ALBUM_ID_FAVORITES:
            path /= album_id
        return str(path.resolve())

    def _unique_id_prefix(self, album_ids: list[str]) -> str:
        """Return a stable, non-sensitive prefix for entity unique IDs."""
        combined = ",".join(sorted(self._album_path(self.folder_path, aid) for aid in album_ids))
        return sha256(combined.encode()).hexdigest()[:12]

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
            self._album_options = await validate_folder_path(self.hass, self.folder_path)
            return self.async_show_form(
                step_id="album_select",
                data_schema=get_album_select_schema(self._album_options),
            )

        album_ids: list[str] = user_input[CONF_ALBUM_ID]
        if not album_ids:
            return self.async_show_form(
                step_id="album_select",
                data_schema=get_album_select_schema(self._album_options),
                errors={"base": "no_albums_selected"},
            )

        # Only block an exact duplicate — same folder path and same set of album IDs.
        selected_paths = sorted(self._album_path(self.folder_path, aid) for aid in album_ids)
        for entry in self._async_current_entries():
            entry_folder = entry.options.get(CONF_FOLDER_PATH, "")
            entry_album_ids = entry.options.get(CONF_ALBUM_ID, [])
            if not isinstance(entry_album_ids, list):
                continue
            entry_paths = sorted(self._album_path(entry_folder, eid) for eid in entry_album_ids)
            if entry_paths == selected_paths:
                return self.async_abort(reason="already_configured")

        if len(album_ids) == 1:
            title = "Local Photos All" if album_ids[0] == CONF_ALBUM_ID_FAVORITES else f"Local Photos {album_ids[0]}"
        else:
            first = "All" if album_ids[0] == CONF_ALBUM_ID_FAVORITES else album_ids[0]
            title = f"Local Photos {first} + {len(album_ids) - 1} more"

        options = {
            CONF_ALBUM_ID: album_ids,
            CONF_FOLDER_PATH: self.folder_path,
            CONF_UNIQUE_ID_PREFIX: self._unique_id_prefix(album_ids),
            CONF_WRITEMETADATA: True,
        }
        return self.async_create_entry(title=title, data={}, options=options)


__all__ = ["LocalPhotosConfigFlowHandler"]
