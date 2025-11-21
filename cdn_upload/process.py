"""Image and video processing for CDN Upload CLI.

Handles WebP conversion, quality optimization, EXIF stripping,
GIF animation preservation, and video to WebP conversion.
"""

from pathlib import Path
from typing import BinaryIO

from PIL import Image


def process_image(
    input_path: Path | BinaryIO,
    quality: int = 75,
    full_resolution: bool = False,
) -> tuple[bytes, tuple[int, int]]:
    """Convert image to optimized WebP format.

    Args:
        input_path: Path to input image or file-like object
        quality: WebP quality 0-100
        full_resolution: If True, skip resizing

    Returns:
        Tuple of (WebP bytes, (width, height))
    """
    raise NotImplementedError("process_image not yet implemented")


def process_gif(
    input_path: Path,
    quality: int = 75,
) -> tuple[bytes, tuple[int, int]]:
    """Convert animated GIF to animated WebP.

    Preserves all frames and animation timing.

    Args:
        input_path: Path to input GIF
        quality: WebP quality 0-100

    Returns:
        Tuple of (WebP bytes, (width, height))
    """
    raise NotImplementedError("process_gif not yet implemented")


def process_video(
    input_path: Path,
    quality: int = 75,
    max_duration: float = 10.0,
) -> tuple[bytes, tuple[int, int]]:
    """Convert video to animated WebP.

    Removes audio, scales to max 720p, samples at 10fps.

    Args:
        input_path: Path to input video
        quality: WebP quality 0-100
        max_duration: Maximum allowed duration in seconds

    Returns:
        Tuple of (WebP bytes, (width, height))

    Raises:
        ValueError: If video exceeds max_duration
    """
    raise NotImplementedError("process_video not yet implemented")


def strip_location_exif(image: Image.Image) -> Image.Image:
    """Remove GPS/location data from image EXIF while preserving other metadata.

    Args:
        image: PIL Image object

    Returns:
        Image with location data removed
    """
    raise NotImplementedError("strip_location_exif not yet implemented")


def calculate_dimensions(
    original_size: tuple[int, int],
    quality: int,
) -> tuple[int, int]:
    """Calculate target dimensions based on quality setting.

    Args:
        original_size: Original (width, height)
        quality: Target quality percentage

    Returns:
        Target (width, height) maintaining aspect ratio
    """
    raise NotImplementedError("calculate_dimensions not yet implemented")


def get_video_duration(input_path: Path) -> float:
    """Get duration of video file in seconds.

    Args:
        input_path: Path to video file

    Returns:
        Duration in seconds
    """
    raise NotImplementedError("get_video_duration not yet implemented")


def detect_file_type(input_path: Path) -> str:
    """Detect file type from path extension.

    Args:
        input_path: Path to file

    Returns:
        One of: 'image', 'gif', 'video', 'document', 'unknown'
    """
    suffix = input_path.suffix.lower()

    if suffix in {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}:
        return 'image'
    elif suffix == '.gif':
        return 'gif'
    elif suffix in {'.mp4', '.mov', '.avi', '.webm'}:
        return 'video'
    elif suffix in {'.md', '.markdown', '.html', '.htm'}:
        return 'document'
    else:
        return 'unknown'
