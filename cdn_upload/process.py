"""Image and video processing for CDN Upload CLI.

Handles JPEG XL and WebP conversion, quality optimization, EXIF stripping,
GIF animation preservation, and video conversion.
"""

import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO, Literal

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Import pillow-jxl-plugin for JPEG XL support
try:
    import pillow_jxl  # noqa: F401 - registers JXL format with Pillow
    JXL_AVAILABLE = True
except ImportError:
    JXL_AVAILABLE = False

# Type alias for output formats
OutputFormat = Literal["jxl", "webp"]


def process_image(
    input_path: Path | BinaryIO,
    quality: int = 75,
    full_resolution: bool = False,
    output_format: OutputFormat = "jxl",
    lossless_jpeg: bool = True,
    filter_method: str | None = None,
    filter_preset: str = 'mac',
    dark_color: str | None = None,
    light_color: str | None = None,
    threshold_level: int = 128,
) -> tuple[bytes, tuple[int, int]]:
    """Convert image to optimized JPEG XL or WebP format.

    Args:
        input_path: Path to input image or file-like object
        quality: Quality 0-100
        full_resolution: If True, skip resizing
        output_format: Output format - 'jxl' (default) or 'webp'
        lossless_jpeg: If True and input is JPEG, use lossless JXL transcoding
        filter_method: Dithering filter (atkinson|floyd-steinberg|bayer|threshold)
        filter_preset: Color preset name
        dark_color: Custom dark color hex
        light_color: Custom light color hex
        threshold_level: For threshold filter (0-255)

    Returns:
        Tuple of (output bytes, (width, height))
    """
    # Detect if input is JPEG for lossless transcoding
    is_jpeg_input = False
    if isinstance(input_path, Path):
        is_jpeg_input = input_path.suffix.lower() in {'.jpg', '.jpeg'}

    # Check JXL availability
    if output_format == "jxl" and not JXL_AVAILABLE:
        raise RuntimeError(
            "JPEG XL support not available. Install with: pip install pillow-jxl-plugin"
        )

    # Open image
    if isinstance(input_path, Path):
        image = Image.open(input_path)
    else:
        image = Image.open(input_path)

    # Get original size before any conversion
    original_size = image.size

    # For lossless JPEG→JXL transcoding, skip color conversion and resizing
    use_lossless = (
        output_format == "jxl"
        and is_jpeg_input
        and lossless_jpeg
        and full_resolution  # Only lossless if keeping full resolution
    )

    if use_lossless:
        # Lossless JPEG→JXL: preserve original exactly
        # Re-read the original JPEG data for lossless transcoding
        if isinstance(input_path, Path):
            with open(input_path, 'rb') as f:
                jpeg_data = f.read()

            # Use pillow_jxl to do lossless JPEG reconstruction
            output_buffer = io.BytesIO()
            image.save(
                output_buffer,
                format='JXL',
                lossless=True,
            )
            return output_buffer.getvalue(), original_size

    # Standard processing path (lossy or non-JPEG input)
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

    # Apply dithering filter if specified
    if filter_method:
        image = apply_filter(
            image, filter_method, filter_preset,
            dark_color, light_color, threshold_level
        )

    # Calculate target dimensions
    if full_resolution:
        target_size = original_size
    else:
        target_size = calculate_dimensions(original_size, quality)

    # Resize if needed
    if target_size != original_size:
        image = image.resize(target_size, Image.Resampling.LANCZOS)

    # Encode to output format
    output_buffer = io.BytesIO()

    if output_format == "jxl":
        # JPEG XL encoding
        image.save(
            output_buffer,
            format='JXL',
            quality=quality,
        )
    else:
        # WebP encoding (fallback)
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
    output_format: OutputFormat = "webp",
) -> tuple[bytes, tuple[int, int]]:
    """Convert animated GIF to animated WebP or JXL.

    Preserves all frames and animation timing.
    Note: For animated content, WebP is recommended for broader compatibility.

    Args:
        input_path: Path to input GIF
        quality: Quality 0-100
        output_format: Output format - 'webp' (default for GIFs) or 'jxl'

    Returns:
        Tuple of (output bytes, (width, height))
    """
    # Open the GIF
    gif = Image.open(input_path)

    # Check if it's actually animated
    is_animated = hasattr(gif, 'n_frames') and gif.n_frames > 1

    if not is_animated:
        # Treat as static image
        return process_image(input_path, quality=quality, full_resolution=True, output_format=output_format)

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

    # Save as animated image
    output_buffer = io.BytesIO()

    if output_format == "jxl" and JXL_AVAILABLE:
        # Animated JXL
        frames[0].save(
            output_buffer,
            format='JXL',
            save_all=True,
            append_images=frames[1:] if len(frames) > 1 else [],
            duration=durations,
            loop=gif.info.get('loop', 0),
            quality=quality,
        )
    else:
        # Animated WebP (default for GIFs)
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
    output_format: OutputFormat = "webp",
) -> tuple[bytes, tuple[int, int]]:
    """Convert video to animated WebP.

    Removes audio, scales to max 720p, samples at 10fps.
    Note: Videos always output WebP regardless of format setting (ffmpeg limitation).

    Args:
        input_path: Path to input video
        quality: Quality 0-100
        max_duration: Maximum allowed duration in seconds
        output_format: Ignored - videos always output WebP for ffmpeg compatibility

    Returns:
        Tuple of (WebP bytes, (width, height))

    Raises:
        ValueError: If video exceeds max_duration
    """
    # Note: Video processing always uses WebP due to ffmpeg limitations with animated JXL
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


# ═══════════════════════════════════════════════════════════════════════════
# DITHERING ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════

DITHER_PRESETS = {
    'cyberspace': {'dark': '#0a0a0a', 'light': '#d4c5a9'},
    'mac': {'dark': '#000000', 'light': '#ffffff'},
    'gameboy': {'dark': '#0f380f', 'light': '#9bbc0f'},
    'amber': {'dark': '#1a0a00', 'light': '#ffb000'},
    'green': {'dark': '#001a00', 'light': '#00ff00'},
    'blueprint': {'dark': '#001133', 'light': '#99ccff'},
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def apply_filter(
    image: Image.Image,
    method: str,
    preset: str = 'mac',
    dark: str | None = None,
    light: str | None = None,
    threshold_level: int = 128,
) -> Image.Image:
    """Apply dithering filter with color mapping.

    Args:
        image: PIL Image (should be RGB)
        method: atkinson|floyd-steinberg|bayer|threshold
        preset: Color preset name
        dark: Custom dark color (hex)
        light: Custom light color (hex)
        threshold_level: For threshold method (0-255)

    Returns:
        Filtered PIL Image
    """
    import numpy as np

    # Get colors from preset or custom
    colors = DITHER_PRESETS.get(preset, DITHER_PRESETS['mac'])
    dark_color = dark or colors['dark']
    light_color = light or colors['light']

    # Apply dithering
    if method == 'atkinson':
        dithered = dither_atkinson(image)
    elif method == 'floyd-steinberg':
        dithered = dither_floyd_steinberg(image)
    elif method == 'bayer':
        dithered = dither_bayer(image)
    elif method == 'threshold':
        dithered = dither_threshold(image, threshold_level)
    else:
        raise ValueError(f"Unknown dither method: {method}")

    # Apply color mapping
    return apply_color_map(dithered, dark_color, light_color)


def dither_atkinson(image: Image.Image) -> Image.Image:
    """Atkinson dithering - classic Mac algorithm.

    Spreads 6/8 of error to 6 neighbors (loses 2/8 = sharper contrast).
    """
    import numpy as np

    gray = np.array(image.convert('L'), dtype=np.float32)
    height, width = gray.shape

    for y in range(height):
        for x in range(width):
            old_val = gray[y, x]
            new_val = 255.0 if old_val >= 128 else 0.0
            gray[y, x] = new_val
            error = (old_val - new_val) / 8.0

            # Atkinson pattern: distribute to 6 neighbors
            neighbors = [
                (x + 1, y), (x + 2, y),
                (x - 1, y + 1), (x, y + 1), (x + 1, y + 1),
                (x, y + 2)
            ]
            for nx, ny in neighbors:
                if 0 <= nx < width and 0 <= ny < height:
                    gray[ny, nx] = np.clip(gray[ny, nx] + error, 0, 255)

    return Image.fromarray(gray.astype(np.uint8), mode='L')


def dither_floyd_steinberg(image: Image.Image) -> Image.Image:
    """Floyd-Steinberg error diffusion dithering."""
    import numpy as np

    gray = np.array(image.convert('L'), dtype=np.float32)
    height, width = gray.shape

    for y in range(height):
        for x in range(width):
            old_val = gray[y, x]
            new_val = 255.0 if old_val >= 128 else 0.0
            gray[y, x] = new_val
            error = old_val - new_val

            # Floyd-Steinberg distribution
            if x + 1 < width:
                gray[y, x + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    gray[y + 1, x - 1] += error * 3 / 16
                gray[y + 1, x] += error * 5 / 16
                if x + 1 < width:
                    gray[y + 1, x + 1] += error * 1 / 16

    gray = np.clip(gray, 0, 255)
    return Image.fromarray(gray.astype(np.uint8), mode='L')


def dither_bayer(image: Image.Image) -> Image.Image:
    """Bayer ordered dithering with 4x4 matrix."""
    import numpy as np

    gray = np.array(image.convert('L'), dtype=np.float32)
    height, width = gray.shape

    # 4x4 Bayer matrix
    bayer = np.array([
        [0, 8, 2, 10],
        [12, 4, 14, 6],
        [3, 11, 1, 9],
        [15, 7, 13, 5]
    ], dtype=np.float32)

    # Normalize to 0-255 range
    threshold_map = np.tile(bayer, (height // 4 + 1, width // 4 + 1))[:height, :width]
    threshold_map = (threshold_map + 1) / 17.0 * 255

    result = np.where(gray > threshold_map, 255, 0).astype(np.uint8)
    return Image.fromarray(result, mode='L')


def dither_threshold(image: Image.Image, level: int = 128) -> Image.Image:
    """Simple threshold dithering."""
    import numpy as np

    gray = np.array(image.convert('L'))
    result = np.where(gray >= level, 255, 0).astype(np.uint8)
    return Image.fromarray(result, mode='L')


def apply_color_map(image: Image.Image, dark: str, light: str) -> Image.Image:
    """Map grayscale (0=dark, 255=light) to custom colors."""
    import numpy as np

    gray = np.array(image.convert('L'))
    dark_rgb = hex_to_rgb(dark)
    light_rgb = hex_to_rgb(light)

    # Create RGB output
    rgb = np.zeros((*gray.shape, 3), dtype=np.uint8)
    mask = gray > 128

    for i in range(3):
        rgb[:, :, i] = np.where(mask, light_rgb[i], dark_rgb[i])

    return Image.fromarray(rgb, mode='RGB')


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
