"""Config flow for Local Photos integration."""
from __future__ import annotations

import logging
import os
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback, HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_WRITEMETADATA,
    WRITEMETADATA_DEFAULT_OPTION,
    CONF_ALBUM_ID,
    CONF_ALBUM_ID_FAVORITES,
    CONF_FOLDER_PATH,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Local Photos."""

    VERSION = 1
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            # Show folder path input form
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_FOLDER_PATH, 
                            default=os.path.join(self.hass.config.config_dir, "www", "images")
                        ): str,
                    }
                ),
            )

        # User has entered a folder path, now show album selection
        folder_path = user_input[CONF_FOLDER_PATH]
        
        # Validate the folder path
        if not os.path.isabs(folder_path):
            folder_path = os.path.join(self.hass.config.config_dir, folder_path)
            
        # Check if the directory exists
        if not os.path.exists(folder_path):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_FOLDER_PATH, 
                            default=folder_path
                        ): str,
                    }
                ),
                errors={"base": "directory_not_found"}
            )
            
        # Store the folder path for later use
        self.folder_path = folder_path
        
        # Move to the album selection step
        return await self.async_step_album_select()
        
    async def async_step_album_select(self, user_input=None):
        """Handle the album selection step."""
        if user_input is None:
            # Show album selection form
            album_schema = await self._get_albumselect_schema()
            return self.async_show_form(
                step_id="album_select",
                data_schema=album_schema,
            )

        # User has selected an album, create the entry
        album_id = user_input[CONF_ALBUM_ID]
        
        # Set title based on album selection
        if album_id == CONF_ALBUM_ID_FAVORITES:
            title = "Local Photos All"
        else:
            title = f"Local Photos {album_id}"
            
        # Create options with the selected album, folder path, and always enable metadata
        options = {
            CONF_ALBUM_ID: [album_id],
            CONF_FOLDER_PATH: self.folder_path,
            CONF_WRITEMETADATA: True  # Always enable metadata
        }

        # Check if an entry with this album already exists
        for entry in self._async_current_entries():
            if entry.options.get(CONF_ALBUM_ID, []) == [album_id]:
                return self.async_abort(reason="already_configured")

        return self.async_create_entry(
            title=title,
            data={},
            options=options,
        )
        
    async def _get_albumselect_schema(self) -> vol.Schema:
        """Return album selection form"""
        # Use the user-specified photos directory
        photos_dir = self.folder_path
        album_selection = {CONF_ALBUM_ID_FAVORITES: "All Photos"}
        
        try:
            # Define a function to run in the executor
            def scan_albums():
                albums_info = {}
                if not os.path.exists(photos_dir):
                    # Create the directory if it doesn't exist
                    os.makedirs(photos_dir)
                    return albums_info
                    
                for item in os.listdir(photos_dir):
                    item_path = os.path.join(photos_dir, item)
                    if os.path.isdir(item_path):
                        # Count the number of image files in the directory
                        image_count = 0
                        for root, _, files in os.walk(item_path):
                            for file in files:
                                if file.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
                                    image_count += 1
                        albums_info[item] = f"{item} ({image_count} items)"
                return albums_info
                
            # Run the file operations in a separate thread
            albums = await self.hass.async_add_executor_job(scan_albums)
            album_selection.update(albums)
        except Exception as err:
            _LOGGER.error("Error scanning albums: %s", err)

        return vol.Schema(
            {
                vol.Required(CONF_ALBUM_ID): vol.In(album_selection),
            }
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for local photos."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self.folder_path = None

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is None:
            # Get current values from config entry
            current_folder_path = self._config_entry.options.get(
                CONF_FOLDER_PATH, 
                os.path.join(self.hass.config.config_dir, "www", "images")
            )
            
            # Show folder path input form
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_FOLDER_PATH, 
                            default=current_folder_path
                        ): str,
                    }
                ),
            )

        # User has entered a folder path, now show album selection
        folder_path = user_input[CONF_FOLDER_PATH]
        
        # Validate the folder path
        if not os.path.isabs(folder_path):
            folder_path = os.path.join(self.hass.config.config_dir, folder_path)
            
        # Check if the directory exists
        if not os.path.exists(folder_path):
            current_folder_path = user_input[CONF_FOLDER_PATH]
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_FOLDER_PATH, 
                            default=current_folder_path
                        ): str,
                    }
                ),
                errors={"base": "directory_not_found"}
            )
            
        # Store the folder path for later use
        self.folder_path = folder_path
        
        # Move to the album selection step
        return await self.async_step_album_select()
        
    async def async_step_album_select(self, user_input=None):
        """Handle the album selection step."""
        if user_input is None:
            # Show album selection form
            album_schema = await self._get_albumselect_schema()
            return self.async_show_form(
                step_id="album_select",
                data_schema=album_schema,
            )

        # User has selected an album, update the options
        album_id = user_input[CONF_ALBUM_ID]
        
        # Create updated options with the selected album and folder path
        updated_options = {
            **self._config_entry.options,
            CONF_ALBUM_ID: [album_id],
            CONF_FOLDER_PATH: self.folder_path,
        }

        return self.async_create_entry(title="", data=updated_options)
        
    async def _get_albumselect_schema(self) -> vol.Schema:
        """Return album selection form"""
        # Use the user-specified photos directory
        photos_dir = self.folder_path
        album_selection = {CONF_ALBUM_ID_FAVORITES: "All Photos"}
        
        # Get current album selection
        current_album_id = self._config_entry.options.get(CONF_ALBUM_ID, [CONF_ALBUM_ID_FAVORITES])
        if isinstance(current_album_id, list) and len(current_album_id) > 0:
            current_album_id = current_album_id[0]
        else:
            current_album_id = CONF_ALBUM_ID_FAVORITES
        
        try:
            # Define a function to run in the executor
            def scan_albums():
                albums_info = {}
                if not os.path.exists(photos_dir):
                    return albums_info
                    
                for item in os.listdir(photos_dir):
                    item_path = os.path.join(photos_dir, item)
                    if os.path.isdir(item_path):
                        # Count the number of image files in the directory
                        image_count = 0
                        for root, _, files in os.walk(item_path):
                            for file in files:
                                if file.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")):
                                    image_count += 1
                        albums_info[item] = f"{item} ({image_count} items)"
                return albums_info
                
            # Run the file operations in a separate thread
            albums = await self.hass.async_add_executor_job(scan_albums)
            album_selection.update(albums)
        except Exception as err:
            _LOGGER.error("Error scanning albums: %s", err)

        return vol.Schema(
            {
                vol.Required(CONF_ALBUM_ID, default=current_album_id): vol.In(album_selection),
            }
        )
