"""AI analysis integrations for CDN Upload CLI.

Handles AI provider abstraction, Claude API, OpenRouter stub,
batch analysis, response parsing, and cache management.
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import anthropic

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
    content_hash: str | None = None,
    provider: str = "claude",
) -> ImageMetadata:
    """Get AI-generated metadata for a single image.

    Args:
        image_data: Image bytes to analyze
        config: AI provider configuration
        content_hash: Optional hash for caching
        provider: AI provider to use ('claude', 'openrouter', 'local')

    Returns:
        ImageMetadata with description, alt_text, and tags
    """
    # Check cache first if hash provided
    if content_hash:
        cached = get_cached_analysis(content_hash)
        if cached:
            return cached

    # Call appropriate provider
    if provider == "claude":
        if not config.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")
        result = _call_claude(image_data, config.anthropic_api_key)
    elif provider == "openrouter":
        if not config.openrouter_api_key:
            raise ValueError("OpenRouter API key not configured")
        result = _call_openrouter(image_data, config.openrouter_api_key)
    elif provider == "local":
        result = _call_local(image_data)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    # Create metadata object
    metadata = ImageMetadata(
        description=result.get("description", ""),
        alt_text=result.get("alt_text", ""),
        tags=result.get("tags", []),
    )

    # Cache result if hash provided
    if content_hash:
        cache_analysis(content_hash, metadata)

    return metadata


def batch_analyze(
    images: list[tuple[str, bytes]],
    config: AIConfig,
    provider: str = "claude",
    max_workers: int = 3,
) -> dict[str, ImageMetadata]:
    """Analyze multiple images efficiently.

    Uses parallel processing for better performance.

    Args:
        images: List of (hash, image_data) tuples
        config: AI provider configuration
        provider: AI provider to use
        max_workers: Maximum parallel requests

    Returns:
        Dictionary mapping hash to ImageMetadata
    """
    results = {}

    # Check cache for all images first
    uncached = []
    for content_hash, image_data in images:
        cached = get_cached_analysis(content_hash)
        if cached:
            results[content_hash] = cached
        else:
            uncached.append((content_hash, image_data))

    # Process uncached images in parallel
    if uncached:
        def analyze_single(content_hash: str, image_data: bytes):
            metadata = analyze_image(image_data, config, content_hash, provider)
            return content_hash, metadata

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for content_hash, image_data in uncached:
                future = executor.submit(analyze_single, content_hash, image_data)
                futures.append(future)

            for future in as_completed(futures):
                content_hash, metadata = future.result()
                results[content_hash] = metadata

    return results


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
    # Initialize client
    client = anthropic.Anthropic(api_key=api_key)

    # Encode image to base64
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")

    # Determine media type (assume WebP for processed images)
    media_type = "image/webp"

    # Make API request
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                ],
            }
        ],
    )

    # Extract text response
    response_text = message.content[0].text

    # Parse JSON from response
    try:
        # Try to find JSON in response
        if "{" in response_text:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        else:
            # If no JSON found, create default response
            return {
                "description": response_text[:100],
                "alt_text": response_text,
                "tags": [],
            }
    except (json.JSONDecodeError, ValueError):
        # Fallback for parsing errors
        return {
            "description": "Image analysis failed",
            "alt_text": response_text[:200] if response_text else "No description available",
            "tags": [],
        }


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
    raise NotImplementedError(
        "OpenRouter integration not yet implemented. "
        "Please use 'claude' as the provider."
    )


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
    raise NotImplementedError(
        "Local model integration not yet implemented. "
        "Please use 'claude' as the provider."
    )


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
