"""Pure image processing functions for local_photos.

All functions in this module are synchronous and should be called via
hass.async_add_executor_job — they must not be called directly from
async context as they perform blocking I/O or CPU-bound PIL operations.
"""

from __future__ import annotations

import io
import logging
import math

from PIL import Image

_LOGGER = logging.getLogger(__name__)

# Resampling filter — Image.Resampling.LANCZOS in Pillow >= 9.1
_LANCZOS = Image.Resampling.LANCZOS


def apply_exif_orientation(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation tag to correct image rotation."""
    try:
        exif_method = getattr(img, "_getexif", None)
        if exif_method is not None:
            exif_data = exif_method()
            if exif_data is not None:
                exif = dict(exif_data.items())
                orientation = exif.get(0x0112, 1)
                T = Image.Transpose
                if orientation == 2:
                    return img.transpose(T.FLIP_LEFT_RIGHT)
                if orientation == 3:
                    return img.transpose(T.ROTATE_180)
                if orientation == 4:
                    return img.transpose(T.FLIP_TOP_BOTTOM)
                if orientation == 5:
                    return img.transpose(T.FLIP_LEFT_RIGHT).transpose(T.ROTATE_90)
                if orientation == 6:
                    return img.transpose(T.ROTATE_270)
                if orientation == 7:
                    return img.transpose(T.FLIP_LEFT_RIGHT).transpose(T.ROTATE_270)
                if orientation == 8:
                    return img.transpose(T.ROTATE_90)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error applying EXIF orientation: %s", err)
    return img


def resize_and_crop_image(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Resize and crop the image to fill the target dimensions exactly."""
    img = apply_exif_orientation(img)
    original_width, original_height = img.size
    original_ratio = original_width / original_height
    target_ratio = target_width / target_height

    if original_ratio > target_ratio:
        resize_height = target_height
        resize_width = int(original_width * (resize_height / original_height))
        img_resized = img.resize((resize_width, resize_height), _LANCZOS)
        left = (resize_width - target_width) // 2
        return img_resized.crop((left, 0, left + target_width, target_height))
    resize_width = target_width
    resize_height = int(original_height * (resize_width / original_width))
    img_resized = img.resize((resize_width, resize_height), _LANCZOS)
    top = (resize_height - target_height) // 2
    return img_resized.crop((0, top, target_width, top + target_height))


def resize_to_fit(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Resize image to fit within target dimensions, adding black letterboxing."""
    img = apply_exif_orientation(img)
    original_width, original_height = img.size
    original_ratio = original_width / original_height
    target_ratio = target_width / target_height

    canvas = Image.new("RGB", (target_width, target_height), (0, 0, 0))

    if original_ratio > target_ratio:
        new_width = target_width
        new_height = int(original_height * (new_width / original_width))
    else:
        new_height = target_height
        new_width = int(original_width * (new_height / original_height))

    img_resized = img.resize((new_width, new_height), _LANCZOS)
    paste_x = (target_width - new_width) // 2
    paste_y = (target_height - new_height) // 2
    canvas.paste(img_resized, (paste_x, paste_y))
    return canvas


def is_portrait(dimensions: tuple[float, float]) -> bool:
    """Return True if the given dimensions represent a portrait orientation."""
    return dimensions[0] < dimensions[1]


def calculate_combined_image_dimensions(target: tuple[float, float], src: tuple[float, float]) -> tuple[float, float]:
    """Calculate the dimensions each half-image should occupy when combining two images."""
    multiplier_width = target[0] / src[0]
    multiplier_height = target[1] / src[1]
    if multiplier_height > multiplier_width:
        return (target[0], target[1] / 2)
    return (target[0] / 2, target[1])


def calculate_cut_loss(target: tuple[float, float], src: tuple[float, float]) -> float:
    """Calculate the fraction of source pixels lost when cropping src to fit target."""
    multiplier = max(target[0] / src[0], target[1] / src[1])
    return 1 - ((target[0] * target[1]) / ((src[0] * multiplier) * (src[1] * multiplier)))


def combine_images(
    primary_data: bytes,
    secondary_data: bytes,
    width: int,
    height: int,
    combined_image_dimensions: tuple[float, float],
    requested_dimensions: tuple[float, float],
) -> bytes:
    """Combine two images side-by-side or stacked, returning JPEG bytes."""
    with Image.new("RGB", (width, height), "white") as output:
        with Image.open(io.BytesIO(primary_data)) as img1:
            img1 = apply_exif_orientation(img1)
            target_w = math.ceil(combined_image_dimensions[0])
            target_h = math.ceil(combined_image_dimensions[1])
            img1 = resize_and_crop_image(img1, target_w, target_h)
            output.paste(img1, (0, 0))

        with Image.open(io.BytesIO(secondary_data)) as img2:
            img2 = apply_exif_orientation(img2)
            target_w = math.ceil(combined_image_dimensions[0])
            target_h = math.ceil(combined_image_dimensions[1])
            img2 = resize_and_crop_image(img2, target_w, target_h)

            if combined_image_dimensions[0] < requested_dimensions[0]:
                output.paste(img2, (math.floor(combined_image_dimensions[0]), 0))
            else:
                output.paste(img2, (0, math.floor(combined_image_dimensions[1])))

        with io.BytesIO() as result:
            output.save(result, "JPEG")
            return result.getvalue()
