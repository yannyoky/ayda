"""Photo cleaning: decode, apply the EXIF orientation, drop every metadata block (GPS
included) and re-encode a resized JPEG. Only the cleaned copy is ever shown."""

import io

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()  # pyright: ignore[reportUnknownMemberType]

MAX_SIDE = 1600
MAX_PIXELS = 50_000_000  # decompression bomb guard
JPEG_QUALITY = 85
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    pass


def clean_photo(data: bytes) -> tuple[bytes, int, int]:
    """Returns (jpeg bytes without metadata, width, height)."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP", "HEIF"):
                raise InvalidImage(source.format or "unknown")
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise InvalidImage(type(exc).__name__) from None
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    # A fresh image carries pixels only: no EXIF, XMP, ICC text or comments.
    clean = Image.new("RGB", image.size)
    clean.paste(image)
    out = io.BytesIO()
    clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), clean.width, clean.height
