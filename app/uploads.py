"""Validated, re-encoded report photos stored outside the static directory."""

from io import BytesIO
from pathlib import Path
from typing import Optional
from uuid import uuid4
import warnings

from flask import current_app

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_PIXELS = 25_000_000


def save_image(upload) -> Optional[str]:
    if upload is None or not upload.filename:
        return None

    extension = Path(upload.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Photo must be a JPG, JPEG, PNG, or WEBP file.")
    normalized_extension = "jpg" if extension == "jpeg" else extension
    try:
        from PIL import Image, ImageOps
        from PIL import ImageFile
    except ImportError as error:
        raise RuntimeError("Pillow is required to process uploaded images.") from error

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    expected_format = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[normalized_extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload.stream) as image:
                if image.format != expected_format:
                    raise ValueError("The uploaded file is not a valid supported image.")
                image.load()
                image = ImageOps.exif_transpose(image)
                has_alpha = "A" in image.getbands() or "transparency" in image.info
                mode = "RGBA" if normalized_extension != "jpg" and has_alpha else "RGB"
                clean_image = image.convert(mode)
                output = BytesIO()
                clean_image.save(output, format=expected_format)
                if output.tell() > 10 * 1024 * 1024:
                    raise ValueError("The processed photo is too large.")
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("The uploaded file is not a valid supported image.") from error

    filename = f"{uuid4().hex}.{normalized_extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    destination.write_bytes(output.getvalue())
    return filename


def delete_image(filename: Optional[str]) -> None:
    if not filename or Path(filename).name != filename:
        return
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    if path.is_file():
        path.unlink()
