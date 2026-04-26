"""Per-album DataUpdateCoordinator for local_photos."""

from __future__ import annotations

from datetime import datetime
import io
import logging
from pathlib import Path
import random
from typing import TYPE_CHECKING, Any

from PIL import Image as PILImage

from custom_components.local_photos.api import Album, LocalPhotosManager, MediaItem
from custom_components.local_photos.const import (
    ASPECT_RATIO_VALUES,
    CONF_ALBUM_ID_FAVORITES,
    DOMAIN,
    MANUFACTURER,
    SETTING_ASPECT_RATIO_DEFAULT_OPTION,
    SETTING_CROP_MODE_COMBINED,
    SETTING_CROP_MODE_CROP,
    SETTING_CROP_MODE_DEFAULT_OPTION,
    SETTING_CROP_MODE_ORIGINAL,
    SETTING_IMAGESELECTION_MODE_ALPHABETICAL,
    SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION,
    SETTING_INTERVAL_DEFAULT_OPTION,
    SETTING_INTERVAL_MAP,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .image_processing import (
    apply_exif_orientation,
    calculate_combined_image_dimensions,
    calculate_cut_loss,
    combine_images,
    is_portrait,
    resize_and_crop_image,
    resize_to_fit,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class LocalPhotosDataUpdateCoordinator(DataUpdateCoordinator):  # type: ignore[type-arg]
    """Coordinates data retrieval and image processing for a single album."""

    _photos_manager: LocalPhotosManager
    _config: ConfigEntry

    album: Album | None = None
    album_id: str
    current_media_primary: MediaItem | None = None
    current_media_secondary: MediaItem | None = None
    current_media_cache: dict[str, bytes]

    current_media_selected_timestamp: datetime

    crop_mode: str
    image_selection_mode: str
    interval: str
    aspect_ratio: str

    def __init__(
        self,
        hass: HomeAssistant,
        photos_manager: LocalPhotosManager,
        config: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the coordinator for a specific album."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self._photos_manager = photos_manager
        self._config = config
        self.album_id = album_id
        self.current_media_cache = {}
        self.current_media_selected_timestamp = datetime.fromtimestamp(0)
        self.crop_mode = SETTING_CROP_MODE_DEFAULT_OPTION
        self.image_selection_mode = SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION
        self.interval = SETTING_INTERVAL_DEFAULT_OPTION
        self.aspect_ratio = SETTING_ASPECT_RATIO_DEFAULT_OPTION

        self.album = self._photos_manager.get_album(album_id)
        if not self.album:
            _LOGGER.warning("Album not found: %s, using default", album_id)
            self.album = self._photos_manager.get_album(CONF_ALBUM_ID_FAVORITES)

    @property
    def current_media(self) -> MediaItem | None:
        """Get the current primary media item."""
        return self.current_media_primary

    @property
    def current_secondary_media(self) -> MediaItem | None:
        """Get the current secondary media item (used in Combine mode)."""
        return self.current_media_secondary

    def get_device_info(self) -> DeviceInfo:
        """Return DeviceInfo for this album's device."""
        if self.album_id == CONF_ALBUM_ID_FAVORITES:
            device_name = "Local Photos All"
        else:
            album_title = self.album.title if self.album else self.album_id
            device_name = f"Local Photos {album_title}"

        return DeviceInfo(
            identifiers={(DOMAIN, self._config.entry_id, self.album_id)},  # type: ignore[arg-type]
            manufacturer=MANUFACTURER,
            name=device_name,
            configuration_url=None,
        )

    def set_crop_mode(self, crop_mode: str) -> None:
        """Set the crop mode and clear the image cache."""
        self.current_media_cache = {}
        self.crop_mode = crop_mode

    def set_image_selection_mode(self, image_selection_mode: str) -> None:
        """Set the image selection mode."""
        self.image_selection_mode = image_selection_mode

    def set_interval(self, interval: str) -> None:
        """Set the update interval and notify listeners."""
        self.interval = interval
        self.async_update_listeners()

    def set_aspect_ratio(self, aspect_ratio: str) -> None:
        """Set the aspect ratio, clear cache, and notify listeners."""
        self.aspect_ratio = aspect_ratio
        self.current_media_cache = {}
        self.async_update_listeners()

    def get_config_option(self, prop: str, default: Any) -> Any:
        """Get a config option from the config entry options."""
        if self._config.options is not None and prop in self._config.options:
            return self._config.options[prop]
        return default

    def current_media_id(self) -> str | None:
        """Return the ID of the current media item."""
        media = self.current_media
        return media.id if media is not None else None

    async def set_current_media_with_id(self, media_id: str | None) -> None:
        """Set the current media using only an ID."""
        if media_id is None:
            return
        try:
            self.current_media_selected_timestamp = datetime.now()
            media = await self._get_media_by_id(media_id)
            self.current_media_primary = media
            self.current_media_secondary = None
            self.current_media_cache = {}
        except Exception as err:
            _LOGGER.error("Error setting current media: %s", err)
            raise UpdateFailed(f"Error setting current media: {err}") from err

    async def _get_media_by_id(self, media_id: str) -> MediaItem | None:
        """Fetch a media item by ID, falling back to random on failure."""
        try:
            media = await self._photos_manager.get_media_item(self.album_id, media_id)
        except Exception as err:
            _LOGGER.error("Error getting media by id: %s", err)
            raise UpdateFailed(f"Error getting media by id: {err}") from err
        else:
            if media is None:
                _LOGGER.warning("Media %s not found in album %s", media_id, self.album_id)
                return await self._get_random_media()
            return media

    async def refresh_current_image(self) -> bool:
        """Advance to the next image if the configured interval has elapsed."""
        interval = SETTING_INTERVAL_MAP.get(self.interval)
        if interval is None:
            return False
        time_delta = (datetime.now() - self.current_media_selected_timestamp).total_seconds()
        if time_delta > interval or self.current_media is None:
            await self.select_next()
            return True
        return False

    async def select_next(self, mode: str | None = None) -> None:
        """Select the next media item based on the current or given mode."""
        mode = mode or self.image_selection_mode
        if mode.lower() == SETTING_IMAGESELECTION_MODE_ALPHABETICAL.lower():
            await self._select_sequential_media()
        else:
            await self._select_random_media()

    async def _select_random_media(self) -> None:
        """Select a random media item."""
        try:
            media = await self._photos_manager.get_random_media_item(self.album_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error selecting random media: %s", err)
        else:
            if media:
                await self.set_current_media_with_id(media.id)
            else:
                _LOGGER.warning("No media found in album %s", self.album_id)

    async def _select_sequential_media(self) -> None:
        """Select the next media item in alphabetical order."""
        try:
            current_media_id = self.current_media_id()
            media = await self._photos_manager.get_next_media_item(self.album_id, current_media_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error selecting sequential media: %s", err)
        else:
            if media:
                await self.set_current_media_with_id(media.id)
            else:
                _LOGGER.warning("No media found in album %s", self.album_id)

    async def _get_random_media(self) -> MediaItem | None:
        """Get a random media item from the album."""
        media = await self._photos_manager.get_random_media_item(self.album_id)
        if not media:
            _LOGGER.warning("No media found in album %s", self.album_id)
        return media

    async def get_media_data(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return binary image data for the current media, processed per crop mode."""
        if self.current_media_primary is None:
            return None

        # Resolve None/zero dimensions from aspect ratio (HA may pass 0 before the
        # frontend knows its target size)
        if not width:
            width = None
        if not height:
            height = None
        if width is None or height is None:
            aspect_ratio_values = ASPECT_RATIO_VALUES.get(self.aspect_ratio, (16, 10))
            if width is None and height is None:
                width = 1920
                height = int(width * aspect_ratio_values[1] / aspect_ratio_values[0])
            elif width is None:
                assert height is not None
                width = int(height * aspect_ratio_values[0] / aspect_ratio_values[1])
            else:
                assert width is not None
                height = int(width * aspect_ratio_values[1] / aspect_ratio_values[0])

        # At this point both width and height are int
        w: int = width
        h: int = height

        cache_key = f"w{w}h{h}{self.crop_mode}{self.aspect_ratio}"
        if cache_key in self.current_media_cache:
            return self.current_media_cache[cache_key]

        if self.crop_mode == SETTING_CROP_MODE_COMBINED:
            result = await self._get_combined_media_data(w, h)
            if result is not None:
                self.async_update_listeners()
                self.current_media_cache[cache_key] = result
                return result

        try:
            path = self.current_media_primary.path
            crop_mode = self.crop_mode

            def read_and_process_image() -> bytes:
                with Path(path).open("rb") as f:
                    image_data = f.read()
                with PILImage.open(io.BytesIO(image_data)) as img:
                    img = apply_exif_orientation(img)
                    if crop_mode == SETTING_CROP_MODE_CROP:
                        img_resized = resize_and_crop_image(img, w, h)
                    elif crop_mode == SETTING_CROP_MODE_ORIGINAL:
                        img_resized = resize_to_fit(img, w, h)
                    else:
                        img_resized = resize_and_crop_image(img, w, h)
                    img_byte_arr = io.BytesIO()
                    # Camera images should be returned in a frontend-friendly
                    # format. Returning HEIC/HEIF bytes works poorly for
                    # standalone camera rendering, while the combined path
                    # already normalizes to JPEG.
                    if img_resized.mode not in ("RGB", "L"):
                        img_resized = img_resized.convert("RGB")
                    img_resized.save(img_byte_arr, format="JPEG", quality=95)
                    return img_byte_arr.getvalue()

            result = await self.hass.async_add_executor_job(read_and_process_image)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error processing image %s: %s", self.current_media_primary.path, err)
            return None
        else:
            self.current_media_cache[cache_key] = result
            self.async_update_listeners()
            return result

    async def _get_combined_media_data(self, width: int, height: int) -> bytes | None:
        """Attempt to combine two orientation-matched images into one frame."""
        requested_dimensions = (float(width), float(height))
        media_dimensions = await self._get_media_dimensions()
        if media_dimensions is None:
            return None

        media_is_portrait = is_portrait(media_dimensions)
        if is_portrait(requested_dimensions) is media_is_portrait:
            return None

        combined_dims = calculate_combined_image_dimensions(requested_dimensions, media_dimensions)
        cut_loss_single = calculate_cut_loss(requested_dimensions, media_dimensions)
        cut_loss_combined = calculate_cut_loss(combined_dims, media_dimensions)
        if cut_loss_single < cut_loss_combined:
            return None

        if self.current_media_secondary is None:
            try:
                all_media = await self._photos_manager.get_media_items(self.album_id)
                current_id = self.current_media_id()
                similar_orientation_media: list[MediaItem] = []

                for media_item in all_media:
                    if media_item.id == current_id:
                        continue
                    try:
                        item_path = media_item.path

                        def get_item_dimensions(path: str) -> tuple[int, int]:
                            with PILImage.open(path) as img:
                                return img.size  # type: ignore[return-value]

                        item_dimensions = await self.hass.async_add_executor_job(get_item_dimensions, item_path)
                        if is_portrait(item_dimensions) == media_is_portrait:
                            similar_orientation_media.append(media_item)
                    except Exception:  # noqa: BLE001
                        continue

                if not similar_orientation_media:
                    return None
                self.current_media_secondary = random.choice(similar_orientation_media)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error finding secondary image: %s", err)
                return None

        try:
            if self.current_media_primary is None:
                return None
            primary_path = self.current_media_primary.path
            assert self.current_media_secondary is not None
            secondary_path = self.current_media_secondary.path
            dims = combined_dims
            req_dims = requested_dimensions

            def process_combined() -> bytes:
                primary_data = Path(primary_path).read_bytes()
                secondary_data = Path(secondary_path).read_bytes()
                return combine_images(primary_data, secondary_data, width, height, dims, req_dims)

            return await self.hass.async_add_executor_job(process_combined)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error creating combined image: %s", err)
            return None

    async def _get_media_dimensions(self, media: MediaItem | None = None) -> tuple[float, float] | None:
        """Get the pixel dimensions of a media item (after EXIF orientation)."""
        media = media or self.current_media
        if media is None:
            return None
        try:
            path = media.path

            def get_dimensions() -> tuple[int, int]:
                with PILImage.open(path) as img:
                    img = apply_exif_orientation(img)
                    return img.size  # type: ignore[return-value]

            return await self.hass.async_add_executor_job(get_dimensions)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error getting image dimensions for %s: %s", media.path, err)
            return None

    async def update_data(self) -> None:
        """Select an initial image if none is currently selected."""
        if self.current_media is None and self.album is not None:
            await self.select_next(None)

    async def _async_update_data(self) -> bool:
        """Refresh album data and advance the current image if needed."""
        try:
            self.album = self._photos_manager.get_album(self.album_id)
            if not self.album:
                _LOGGER.warning("Album not found: %s, using default", self.album_id)
                self.album = self._photos_manager.get_album(CONF_ALBUM_ID_FAVORITES)
            await self.update_data()
        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            raise UpdateFailed(f"Error updating data: {err}") from err
        else:
            return True
