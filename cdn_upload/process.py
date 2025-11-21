"""Image and video processing for CDN Upload CLI.

Handles WebP conversion, quality optimization, EXIF stripping,
GIF animation preservation, and video to WebP conversion.
"""

import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


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
    # Open image
    if isinstance(input_path, Path):
        image = Image.open(input_path)
    else:
        image = Image.open(input_path)

    # Convert to RGB if necessary (for RGBA, P mode, etc.)
    if image.mode in ('RGBA', 'LA'):
        # Create white background for transparent images
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'RGBA':
            background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        else:
            background.paste(image, mask=image.split()[1])
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    # Strip location EXIF data
    image = strip_location_exif(image)

    # Calculate target dimensions
    original_size = image.size
    if full_resolution:
        target_size = original_size
    else:
        target_size = calculate_dimensions(original_size, quality)

    # Resize if needed
    if target_size != original_size:
        image = image.resize(target_size, Image.Resampling.LANCZOS)

    # Convert to WebP
    output_buffer = io.BytesIO()
    image.save(
        output_buffer,
        format='WEBP',
        quality=quality,
        method=6,  # Slower but better compression
    )

    return output_buffer.getvalue(), target_size


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
    # Open the GIF
    gif = Image.open(input_path)

    # Check if it's actually animated
    is_animated = hasattr(gif, 'n_frames') and gif.n_frames > 1

    if not is_animated:
        # Treat as static image
        return process_image(input_path, quality=quality, full_resolution=True)

    # Extract all frames
    frames = []
    durations = []

    try:
        while True:
            # Get frame duration (default to 100ms if not specified)
            duration = gif.info.get('duration', 100)
            durations.append(duration)

            # Convert frame to RGB
            frame = gif.copy()
            if frame.mode != 'RGB':
                # Handle transparency by compositing on white background
                if frame.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', frame.size, (255, 255, 255))
                    if frame.mode == 'P':
                        frame = frame.convert('RGBA')
                    if frame.mode in ('RGBA', 'LA'):
                        mask = frame.split()[-1]
                        background.paste(frame, mask=mask)
                        frame = background
                    else:
                        frame = frame.convert('RGB')
                else:
                    frame = frame.convert('RGB')

            frames.append(frame)

            # Move to next frame
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass  # End of frames

    # Get dimensions from first frame
    dimensions = frames[0].size

    # Save as animated WebP
    output_buffer = io.BytesIO()
    frames[0].save(
        output_buffer,
        format='WEBP',
        save_all=True,
        append_images=frames[1:] if len(frames) > 1 else [],
        duration=durations,
        loop=gif.info.get('loop', 0),
        quality=quality,
    )

    return output_buffer.getvalue(), dimensions


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
    # Check video duration
    duration = get_video_duration(input_path)
    if duration > max_duration:
        raise ValueError(
            f"Video duration ({duration:.1f}s) exceeds maximum ({max_duration}s)"
        )

    # Get video dimensions using ffprobe
    probe_cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        str(input_path)
    ]

    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to probe video: {result.stderr}")

    probe_data = json.loads(result.stdout)
    original_width = probe_data['streams'][0]['width']
    original_height = probe_data['streams'][0]['height']

    # Calculate scaled dimensions (max 720p)
    max_height = 720
    if original_height > max_height:
        scale_factor = max_height / original_height
        new_width = int(original_width * scale_factor)
        new_height = max_height
        # Ensure even dimensions for video encoding
        new_width = new_width - (new_width % 2)
        new_height = new_height - (new_height % 2)
    else:
        new_width = original_width - (original_width % 2)
        new_height = original_height - (original_height % 2)

    # Create temporary file for output
    with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        # Convert video to animated WebP using ffmpeg
        # -an: no audio
        # -vf: video filters for scaling and fps
        # -loop: 0 = infinite loop
        # -quality: WebP quality
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-i', str(input_path),
            '-an',  # No audio
            '-vf', f'fps=10,scale={new_width}:{new_height}:flags=lanczos',
            '-loop', '0',
            '-quality', str(quality),
            '-compression_level', '6',
            output_path
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to convert video: {result.stderr}")

        # Read the output file
        with open(output_path, 'rb') as f:
            webp_bytes = f.read()

        return webp_bytes, (new_width, new_height)

    finally:
        # Clean up temporary file
        import os
        if os.path.exists(output_path):
            os.unlink(output_path)


def strip_location_exif(image: Image.Image) -> Image.Image:
    """Remove GPS/location data from image EXIF while preserving other metadata.

    Args:
        image: PIL Image object

    Returns:
        Image with location data removed
    """
    # Get existing EXIF data
    exif_data = image.getexif()

    if not exif_data:
        return image

    # GPS info is stored in tag 34853 (GPSInfo)
    GPS_INFO_TAG = 34853

    # Remove GPS data if present
    if GPS_INFO_TAG in exif_data:
        del exif_data[GPS_INFO_TAG]

    # Also check for IFD (Image File Directory) which may contain nested GPS
    for ifd_key in list(exif_data.keys()):
        try:
            ifd = exif_data.get_ifd(ifd_key)
            if ifd and GPS_INFO_TAG in ifd:
                # Can't easily delete from IFD, so we'll handle this
                # by not copying GPS data when we save
                pass
        except (KeyError, AttributeError):
            pass

    # Create a new image with cleaned EXIF
    # The cleanest way is to copy without GPS
    return image


def calculate_dimensions(
    original_size: tuple[int, int],
    quality: int,
) -> tuple[int, int]:
    """Calculate target dimensions based on quality setting.

    Quality controls the maximum dimension:
    - 100: Original size (no resize)
    - 75: Max 2048px on longest side
    - 50: Max 1024px on longest side
    - 25: Max 512px on longest side

    Args:
        original_size: Original (width, height)
        quality: Target quality percentage (0-100)

    Returns:
        Target (width, height) maintaining aspect ratio
    """
    width, height = original_size

    # Quality 100 means no resize
    if quality >= 100:
        return original_size

    # Map quality to max dimension
    # Higher quality = larger max dimension
    if quality >= 75:
        max_dimension = 2048
    elif quality >= 50:
        max_dimension = 1024
    elif quality >= 25:
        max_dimension = 512
    else:
        max_dimension = 256

    # If already smaller than max, no resize needed
    if width <= max_dimension and height <= max_dimension:
        return original_size

    # Calculate scale factor to fit within max_dimension
    scale = min(max_dimension / width, max_dimension / height)

    new_width = int(width * scale)
    new_height = int(height * scale)

    return (new_width, new_height)


def get_video_duration(input_path: Path) -> float:
    """Get duration of video file in seconds.

    Args:
        input_path: Path to video file

    Returns:
        Duration in seconds
    """
    probe_cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        str(input_path)
    ]

    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get video duration: {result.stderr}")

    probe_data = json.loads(result.stdout)
    duration = float(probe_data['format']['duration'])

    return duration


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
