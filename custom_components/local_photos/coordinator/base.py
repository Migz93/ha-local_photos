"""Per-album coordinator with scheduled, look-ahead photo rendering."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import random
from typing import TYPE_CHECKING, Any

from custom_components.local_photos.api import LocalPhotosManager, MediaItem
from custom_components.local_photos.const import (
    ASPECT_RATIO_VALUES,
    CONF_ALBUM_ID_FAVORITES,
    CONF_UNIQUE_ID_PREFIX,
    DOMAIN,
    MANUFACTURER,
    MAX_OUTPUT_LONG_EDGE,
    MAX_RENDER_CACHE_BYTES,
    SETTING_ASPECT_RATIO_DEFAULT_OPTION,
    SETTING_CROP_MODE_COMBINED,
    SETTING_CROP_MODE_DEFAULT_OPTION,
    SETTING_CROP_MODE_ORIGINAL,
    SETTING_IMAGESELECTION_MODE_ALPHABETICAL,
    SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION,
    SETTING_INTERVAL_DEFAULT_OPTION,
    SETTING_INTERVAL_MAP,
)
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .image_processing import is_portrait, render_combined, render_single

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedFrame:
    """A fully rendered frame ready to be served by the camera."""

    primary: MediaItem
    secondary: MediaItem | None
    image: bytes


class LocalPhotosDataUpdateCoordinator(DataUpdateCoordinator[bool]):
    """Coordinate a catalogued album and one-frame look-ahead renderer."""

    def __init__(
        self,
        hass: HomeAssistant,
        photos_manager: LocalPhotosManager,
        config: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize a coordinator for one selected album."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self._photos_manager = photos_manager
        self._config = config
        self.album_id = album_id
        self.album = self._photos_manager.get_album(album_id)
        self.current_media_primary: MediaItem | None = None
        self.current_media_secondary: MediaItem | None = None
        self._current_frame: bytes | None = None
        self._next_frame: PreparedFrame | None = None
        self._prepare_task: asyncio.Task[None] | None = None
        self._interval_unsub: CALLBACK_TYPE | None = None
        self._swap_due = False
        self._render_generation = 0
        self._failed_fingerprints: set[str] = set()
        self._state_lock = asyncio.Lock()
        self.crop_mode = SETTING_CROP_MODE_DEFAULT_OPTION
        self.image_selection_mode = SETTING_IMAGESELECTION_MODE_DEFAULT_OPTION
        self.interval = SETTING_INTERVAL_DEFAULT_OPTION
        self.aspect_ratio = SETTING_ASPECT_RATIO_DEFAULT_OPTION

    @property
    def current_media(self) -> MediaItem | None:
        """Return the currently displayed primary source."""
        return self.current_media_primary

    @property
    def current_secondary_media(self) -> MediaItem | None:
        """Return the currently displayed secondary source, if combined."""
        return self.current_media_secondary

    def get_device_info(self) -> DeviceInfo:
        """Return device metadata for this album."""
        album_title = self.album.title if self.album else self.album_id
        name = "Local Photos All" if self.album_id == CONF_ALBUM_ID_FAVORITES else f"Local Photos {album_title}"
        return DeviceInfo(
            identifiers={(DOMAIN, self._config.entry_id, self.album_id)},  # type: ignore[arg-type]
            manufacturer=MANUFACTURER,
            name=name,
        )

    def get_entity_unique_id(self, suffix: str | None = None) -> str:
        """Return a stable entity unique ID without changing legacy IDs."""
        prefix = self._config.options.get(CONF_UNIQUE_ID_PREFIX)
        base = f"{prefix}-{self.album_id}" if isinstance(prefix, str) and prefix else self.album_id
        return base if suffix is None else f"{base}-{suffix}"

    def get_config_option(self, prop: str, default: Any) -> Any:
        """Return an entry option with a fallback."""
        return self._config.options.get(prop, default)

    def set_crop_mode(self, crop_mode: str) -> None:
        """Set crop mode and render the current frame in the background."""
        self.crop_mode = crop_mode
        self._discard_prepared_next()
        self._schedule_current_rerender()

    def set_image_selection_mode(self, image_selection_mode: str) -> None:
        """Set the source selection order."""
        self.image_selection_mode = image_selection_mode
        self._discard_prepared_next()

    def set_interval(self, interval: str) -> None:
        """Set the swap interval and replace the schedule."""
        self.interval = interval
        self._reschedule_interval()
        self.async_update_listeners()

    def set_aspect_ratio(self, aspect_ratio: str) -> None:
        """Set target aspect ratio and render the current frame in the background."""
        self.aspect_ratio = aspect_ratio
        self._discard_prepared_next()
        self._schedule_current_rerender()

    def _discard_prepared_next(self) -> None:
        """Drop work made with settings that no longer apply."""
        self._render_generation += 1
        self._next_frame = None
        if self._prepare_task is not None and not self._prepare_task.done():
            self._prepare_task.cancel()
        self._prepare_task = None

    async def async_start(self) -> None:
        """Render an initial frame and begin background preparation."""
        if self.current_media is None:
            await self._prepare_initial_frame()
        self._reschedule_interval()
        self._ensure_next_preparing()

    async def async_shutdown(self) -> None:
        """Cancel scheduled callbacks and background rendering on unload."""
        if self._interval_unsub is not None:
            self._interval_unsub()
            self._interval_unsub = None
        if self._prepare_task is not None:
            self._prepare_task.cancel()
            await asyncio.gather(self._prepare_task, return_exceptions=True)
            self._prepare_task = None

    def _render_dimensions(self) -> tuple[int, int]:
        ratio_width, ratio_height = ASPECT_RATIO_VALUES.get(self.aspect_ratio, (16, 10))
        return MAX_OUTPUT_LONG_EDGE, MAX_OUTPUT_LONG_EDGE * ratio_height // ratio_width

    async def _prepare_initial_frame(self) -> None:
        frame = await self._build_frame(exclude_id=None)
        if frame is None:
            _LOGGER.warning("No usable photos found in album %s", self.album_id)
            return
        await self._activate_frame(frame)

    async def _build_frame(self, exclude_id: str | None) -> PreparedFrame | None:
        """Select and render a valid candidate, trying each catalog asset once."""
        all_items = await self._photos_manager.get_media_items(self.album_id)
        candidates = [
            item for item in all_items if item.id != exclude_id and item.fingerprint not in self._failed_fingerprints
        ]
        if self.image_selection_mode == SETTING_IMAGESELECTION_MODE_ALPHABETICAL:
            all_items.sort(key=lambda item: item.filename.lower())
            if exclude_id is not None:
                current_index = next((i for i, item in enumerate(all_items) if item.id == exclude_id), -1)
                ordered_items = all_items[current_index + 1 :] + all_items[: current_index + 1]
                candidates = [
                    item
                    for item in ordered_items
                    if item.id != exclude_id and item.fingerprint not in self._failed_fingerprints
                ]
        else:
            random.shuffle(candidates)
        for primary in candidates:
            secondary = self._select_secondary(primary, candidates)
            frame = await self._render_frame(primary, secondary)
            if frame is not None:
                return frame
            self._failed_fingerprints.add(primary.fingerprint)
            _LOGGER.debug("Skipping %s after render failure", primary.path)
        return None

    def _select_secondary(self, primary: MediaItem, candidates: list[MediaItem]) -> MediaItem | None:
        """Choose a catalogued orientation match only when Combine benefits."""
        if self.crop_mode != SETTING_CROP_MODE_COMBINED or primary.dimensions is None:
            return None
        target = self._render_dimensions()
        if is_portrait(primary.dimensions) == is_portrait(target):
            return None
        if not self._combine_is_beneficial(target, primary.dimensions):
            return None
        matches = [
            item
            for item in candidates
            if item.id != primary.id
            and item.dimensions
            and is_portrait(item.dimensions) == is_portrait(primary.dimensions)
        ]
        return random.choice(matches) if matches else None

    @staticmethod
    def _combine_is_beneficial(target: tuple[int, int], source: tuple[int, int]) -> bool:
        """Return whether splitting the target discards no more source than one crop."""
        target_width, target_height = target
        source_width, source_height = source
        if target_height / source_height > target_width / source_width:
            half_target = (target_width, target_height / 2)
        else:
            half_target = (target_width / 2, target_height)

        def cut_loss(frame: tuple[float, float]) -> float:
            multiplier = max(frame[0] / source_width, frame[1] / source_height)
            return 1 - (frame[0] * frame[1]) / ((source_width * multiplier) * (source_height * multiplier))

        return cut_loss(half_target) <= cut_loss((target_width, target_height))

    async def _render_frame(self, primary: MediaItem, secondary: MediaItem | None) -> PreparedFrame | None:
        width, height = self._render_dimensions()
        try:
            if secondary is not None:
                vertical_split = is_portrait((width, height))
                image = await self.hass.async_add_executor_job(
                    render_combined,
                    primary.path,
                    secondary.path,
                    width,
                    height,
                    vertical_split,
                )
            else:
                image = await self.hass.async_add_executor_job(
                    render_single,
                    primary.path,
                    width,
                    height,
                    self.crop_mode != SETTING_CROP_MODE_ORIGINAL,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not render %s: %s", primary.path, err)
            return None
        if len(image) > MAX_RENDER_CACHE_BYTES // 2:
            _LOGGER.debug("Skipping %s: rendered frame exceeds the cache safety limit", primary.path)
            return None
        return PreparedFrame(primary=primary, secondary=secondary, image=image)

    async def _activate_frame(self, frame: PreparedFrame) -> None:
        async with self._state_lock:
            self.current_media_primary = frame.primary
            self.current_media_secondary = frame.secondary
            self._current_frame = frame.image
            self._next_frame = None
            self._swap_due = False
        self.async_update_listeners()

    def _ensure_next_preparing(self) -> None:
        if self._prepare_task is None or self._prepare_task.done():
            self._prepare_task = self.hass.async_create_task(self._async_prepare_next())

    async def _async_prepare_next(self) -> None:
        generation = self._render_generation
        current_id = self.current_media_primary.id if self.current_media_primary else None
        frame = await self._build_frame(exclude_id=current_id)
        if frame is None or generation != self._render_generation:
            return
        async with self._state_lock:
            self._next_frame = frame
            swap_due = self._swap_due
        if swap_due:
            await self._swap_if_ready()

    async def _swap_if_ready(self) -> None:
        async with self._state_lock:
            frame = self._next_frame
            if frame is None:
                self._swap_due = True
                return
        await self._activate_frame(frame)
        self.hass.loop.call_soon(self._ensure_next_preparing)

    @callback
    def _interval_elapsed(self, now: datetime) -> None:
        """Swap only a ready frame; retain the current one otherwise."""
        self.hass.async_create_task(self._swap_if_ready())

    def _reschedule_interval(self) -> None:
        if self._interval_unsub is not None:
            self._interval_unsub()
            self._interval_unsub = None
        seconds = SETTING_INTERVAL_MAP.get(self.interval)
        if seconds is not None:
            self._interval_unsub = async_track_time_interval(
                self.hass, self._interval_elapsed, timedelta(seconds=seconds)
            )

    def _schedule_current_rerender(self) -> None:
        """Render settings changes in background without blanking the camera."""
        if self.current_media_primary is None:
            return
        primary = self.current_media_primary
        secondary = self.current_media_secondary

        async def rerender() -> None:
            frame = await self._render_frame(primary, secondary)
            if frame is not None:
                await self._activate_frame(frame)
                self._ensure_next_preparing()

        self.hass.async_create_task(rerender())

    async def select_next(self, mode: str | None = None) -> None:
        """Immediately request a new prepared frame for the next-media action."""
        if mode is not None:
            self.image_selection_mode = mode
            self._discard_prepared_next()
        if self._next_frame is None:
            self._discard_prepared_next()
            await self._async_prepare_next()
        await self._swap_if_ready()

    async def set_current_media_with_id(self, media_id: str | None) -> None:
        """Select a requested catalog item, retaining the old frame on failure."""
        if media_id is None:
            return
        item = await self._photos_manager.get_media_item(self.album_id, media_id)
        if item is None:
            raise UpdateFailed(f"Media {media_id} not found in album {self.album_id}")
        self._discard_prepared_next()
        frame = await self._render_frame(
            item, self._select_secondary(item, await self._photos_manager.get_media_items(self.album_id))
        )
        if frame is not None:
            await self._activate_frame(frame)
            self._ensure_next_preparing()

    async def refresh_current_image(self) -> bool:
        """Compatibility shim; scheduled rendering owns interval advancement."""
        return False

    async def get_media_data(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return the prepared JPEG; Home Assistant scales it if requested."""
        if self._current_frame is None:
            await self._prepare_initial_frame()
        return self._current_frame

    async def _async_update_data(self) -> bool:
        self.album = self._photos_manager.get_album(self.album_id)
        if self.album is None:
            raise UpdateFailed(f"Album not found: {self.album_id}")
        await self.async_start()
        return self.current_media is not None
