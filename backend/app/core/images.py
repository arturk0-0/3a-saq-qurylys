"""Coordinate Pillow's process-wide decoder option with lazy PDF initialization."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

from PIL import ImageFile

IMAGE_DECODER_LOCK = RLock()


@contextmanager
def strict_image_validation() -> Iterator[None]:
    # Importing WeasyPrint enables truncated-image decoding globally. Temporarily
    # restore Pillow's strict default, without changing the PDF library's setting.
    with IMAGE_DECODER_LOCK:
        previous = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            yield
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous
