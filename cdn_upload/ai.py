"""AI analysis integrations for CDN Upload CLI.

Handles AI provider abstraction, Claude API, OpenRouter stub,
batch analysis, response parsing, and cache management.
"""

import json
from pathlib import Path
from typing import Any

from .config import get_cache_dir
from .models import ImageMetadata, AIConfig


# AI Analysis Prompt
ANALYSIS_PROMPT = """Analyze this image and provide:
1. A concise description (maximum 15 words)
2. Detailed alt text for accessibility (1-2 sentences)
3. 3-5 relevant tags for categorization

Return as JSON:
{
  "description": "...",
  "alt_text": "...",
  "tags": ["tag1", "tag2", ...]
}"""


def analyze_image(
    image_data: bytes,
    config: AIConfig,
    provider: str = "claude",
) -> ImageMetadata:
    """Get AI-generated metadata for a single image.

    Args:
        image_data: Image bytes to analyze
        config: AI provider configuration
        provider: AI provider to use ('claude', 'openrouter', 'local')

    Returns:
        ImageMetadata with description, alt_text, and tags
    """
    raise NotImplementedError("analyze_image not yet implemented")


def batch_analyze(
    images: list[tuple[str, bytes]],
    config: AIConfig,
    provider: str = "claude",
) -> dict[str, ImageMetadata]:
    """Analyze multiple images efficiently.

    Uses batch API if provider supports it, otherwise parallel processing.

    Args:
        images: List of (hash, image_data) tuples
        config: AI provider configuration
        provider: AI provider to use

    Returns:
        Dictionary mapping hash to ImageMetadata
    """
    raise NotImplementedError("batch_analyze not yet implemented")


def _call_claude(
    image_data: bytes,
    api_key: str,
) -> dict[str, Any]:
    """Make Claude API request for image analysis.

    Args:
        image_data: Image bytes to analyze
        api_key: Anthropic API key

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    raise NotImplementedError("_call_claude not yet implemented")


def _call_openrouter(
    image_data: bytes,
    api_key: str,
) -> dict[str, Any]:
    """Make OpenRouter API request for image analysis.

    Stub implementation for future use.

    Args:
        image_data: Image bytes to analyze
        api_key: OpenRouter API key

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    raise NotImplementedError("OpenRouter integration not yet implemented")


def _call_local(
    image_data: bytes,
) -> dict[str, Any]:
    """Make local model request for image analysis.

    Stub implementation for future MLX/LM Studio integration.

    Args:
        image_data: Image bytes to analyze

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    raise NotImplementedError("Local model integration not yet implemented")


def load_cache() -> dict[str, dict[str, Any]]:
    """Load analysis cache from disk.

    Returns:
        Dictionary mapping content hash to cached analysis
    """
    cache_file = get_cache_dir() / "analysis.json"

    if not cache_file.exists():
        return {}

    try:
        with open(cache_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    """Save analysis cache to disk.

    Args:
        cache: Dictionary mapping content hash to analysis
    """
    cache_file = get_cache_dir() / "analysis.json"

    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2)


def get_cached_analysis(content_hash: str) -> ImageMetadata | None:
    """Get cached analysis for a content hash.

    Args:
        content_hash: SHA-256 hash prefix of image content

    Returns:
        Cached ImageMetadata if found, None otherwise
    """
    cache = load_cache()

    if content_hash in cache:
        data = cache[content_hash]
        return ImageMetadata(
            description=data["description"],
            alt_text=data["alt_text"],
            tags=data.get("tags", []),
        )

    return None


def cache_analysis(content_hash: str, metadata: ImageMetadata) -> None:
    """Cache analysis results for a content hash.

    Args:
        content_hash: SHA-256 hash prefix of image content
        metadata: Analysis results to cache
    """
    cache = load_cache()

    cache[content_hash] = {
        "description": metadata.description,
        "alt_text": metadata.alt_text,
        "tags": metadata.tags,
    }

    save_cache(cache)
