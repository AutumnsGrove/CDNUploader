"""Storage utilities for CDN Upload CLI.

Handles content hash calculation, file naming, category determination,
date path generation, and filename sanitization.
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path


def calculate_hash(data: bytes) -> str:
    """Calculate SHA-256 hash and return first 8 characters.

    Args:
        data: File content as bytes

    Returns:
        First 8 characters of hex-encoded SHA-256 hash
    """
    return hashlib.sha256(data).hexdigest()[:8]


def generate_filename(
    original_name: str,
    content_hash: str,
    description: str | None = None,
    extension: str = ".webp",
) -> str:
    """Generate final filename for CDN storage.

    With AI description: photo_of_Sunset_Beach_a3f9b2c1.webp
    Without: a3f9b2c1_original_filename.webp

    Args:
        original_name: Original filename (without extension)
        content_hash: First 8 chars of content hash
        description: Optional AI-generated description
        extension: File extension to use (default: .webp)

    Returns:
        Generated filename with specified extension
    """
    if description:
        # Use AI description
        sanitized = sanitize_name(description, max_length=50)
        return f"{sanitized}_{content_hash}{extension}"
    else:
        # Use original name
        sanitized = sanitize_name(original_name, max_length=50)
        return f"{content_hash}_{sanitized}{extension}"


def determine_category(file_path: Path, override: str | None = None) -> str:
    """Determine storage category for a file.

    Args:
        file_path: Path to file
        override: Optional category override from CLI flag

    Returns:
        Category string (photos, videos, gifs, etc.)
    """
    if override:
        return override

    suffix = file_path.suffix.lower()

    if suffix in {'.mp4', '.mov', '.avi', '.webm'}:
        return 'videos'
    elif suffix == '.gif':
        return 'gifs'
    else:
        return 'photos'


def sanitize_name(name: str, max_length: int = 50) -> str:
    """Sanitize a string for use in URLs/filenames.

    Converts to snake_case, removes special characters,
    and truncates to max length.

    Args:
        name: String to sanitize
        max_length: Maximum length of result

    Returns:
        Sanitized string suitable for URLs
    """
    # Convert to lowercase
    result = name.lower()

    # Replace spaces and hyphens with underscores
    result = re.sub(r'[\s-]+', '_', result)

    # Remove non-alphanumeric characters (except underscores)
    result = re.sub(r'[^\w]', '', result)

    # Collapse multiple underscores
    result = re.sub(r'_+', '_', result)

    # Remove leading/trailing underscores
    result = result.strip('_')

    # Truncate to max length
    if len(result) > max_length:
        result = result[:max_length].rstrip('_')

    return result


def get_date_path(dt: datetime | None = None) -> str:
    """Generate date-based path component.

    Args:
        dt: Datetime to use (defaults to now)

    Returns:
        Path string in format YYYY/MM/DD
    """
    if dt is None:
        dt = datetime.now()

    return f"{dt.year}/{dt.month:02d}/{dt.day:02d}"


def build_object_key(
    category: str,
    date_path: str,
    filename: str,
) -> str:
    """Build complete object key for R2 storage.

    Args:
        category: File category (photos, videos, etc.)
        date_path: Date path (YYYY/MM/DD)
        filename: Final filename

    Returns:
        Complete object key (e.g., photos/2025/03/16/sunset_a3f9b2c1.webp)
    """
    return f"{category}/{date_path}/{filename}"
