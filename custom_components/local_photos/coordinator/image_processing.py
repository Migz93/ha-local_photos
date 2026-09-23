"""Synchronous, bounded image rendering helpers.

Call these helpers through ``hass.async_add_executor_job`` only.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageOps

_LANCZOS = Image.Resampling.LANCZOS


def is_portrait(dimensions: tuple[int, int]) -> bool:
    """Return whether dimensions describe a portrait image."""
    return dimensions[0] < dimensions[1]


def _open_oriented(path: str, target_size: tuple[int, int]) -> Image.Image:
    """Open, decoder-downsample where supported, and orient an image once."""
    with Image.open(Path(path)) as source:
        # Pillow implements ``draft`` for JPEG and plugins may use it to select
        # an embedded thumbnail. Other decoders safely ignore the request.
        source.draft("RGB", target_size)
        return ImageOps.exif_transpose(source).copy()


def _cover_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    """Efficiently resize an image to cover a target frame then crop it."""
    source_width, source_height = image.size
    scale = max(width / source_width, height / source_height)
    cover_size = (math.ceil(source_width * scale), math.ceil(source_height * scale))
    image.thumbnail(cover_size, _LANCZOS, reducing_gap=2.0)
    # ``draft`` may have selected a decoder-sized JPEG/HEIF thumbnail that is
    # smaller than the requested frame. ``thumbnail`` never enlarges it, and a
    # crop outside its bounds would be padded black. Upscale only in that case.
    if image.width < width or image.height < height:
        scale = max(width / image.width, height / image.height)
        image = image.resize((math.ceil(image.width * scale), math.ceil(image.height * scale)), _LANCZOS)
    left = max((image.width - width) // 2, 0)
    top = max((image.height - height) // 2, 0)
    return image.crop((left, top, left + width, top + height))


def _fit_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    """Resize into a black letterboxed frame."""
    image.thumbnail((width, height), _LANCZOS, reducing_gap=2.0)
    canvas = Image.new("RGB", (width, height), "black")
    if image.mode != "RGB":
        image = image.convert("RGB")
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def _jpeg_bytes(image: Image.Image) -> bytes:
    """Encode frontend-compatible JPEG bytes."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def render_single(path: str, width: int, height: int, crop: bool) -> bytes:
    """Render one source image into a JPEG display frame."""
    image = _open_oriented(path, (width, height))
    return _jpeg_bytes(_cover_resize(image, width, height) if crop else _fit_resize(image, width, height))


def render_combined(
    primary_path: str,
    secondary_path: str,
    width: int,
    height: int,
    vertical_split: bool,
) -> bytes:
    """Render two sources side-by-side or stacked into one JPEG frame."""
    output = Image.new("RGB", (width, height), "white")
    if vertical_split:
        first_size = (width, height // 2)
        second_size = (width, height - first_size[1])
        second_position = (0, first_size[1])
    else:
        first_size = (width // 2, height)
        second_size = (width - first_size[0], height)
        second_position = (first_size[0], 0)
    output.paste(_cover_resize(_open_oriented(primary_path, first_size), *first_size), (0, 0))
    output.paste(_cover_resize(_open_oriented(secondary_path, second_size), *second_size), second_position)
    return _jpeg_bytes(output)
