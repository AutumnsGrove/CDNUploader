"""AI analysis integrations for CDN Upload CLI.

Handles AI provider abstraction with multiple backends:
- OpenRouter (primary) - Claude Haiku 4.5 via unified API
- Cloudflare Workers AI (fallback) - near-zero cost
- Anthropic (tertiary) - direct Claude API
- MLX (local) - Apple Silicon only
"""

import base64
import io
import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image

from .config import get_cache_dir
from .models import ImageMetadata, AIConfig

# OpenRouter model (primary) - Claude Haiku 4.5 with vision support
OPENROUTER_MODEL = "anthropic/claude-haiku-4.5"

# Cloudflare Workers AI model (fallback)
CLOUDFLARE_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"

# MLX model configuration
# Default MLX model - can be overridden via environment or config
MLX_MODEL_NAME = "mlx-community/Qwen3-VL-8B-Instruct-8bit"
# Cache for loaded MLX model to avoid reloading
_mlx_model_cache: dict[str, Any] = {}


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
    provider: str = "openrouter",
) -> ImageMetadata:
    """Get AI-generated metadata for a single image.

    Args:
        image_data: Image bytes to analyze
        config: AI provider configuration
        content_hash: Optional hash for caching
        provider: AI provider to use ('openrouter', 'cloudflare', 'claude', 'mlx')

    Returns:
        ImageMetadata with description, alt_text, and tags
    """
    # Check cache first if hash provided
    if content_hash:
        cached = get_cached_analysis(content_hash)
        if cached:
            return cached

    # Call appropriate provider
    if provider == "openrouter":
        if not config.openrouter_api_key:
            raise ValueError("OpenRouter API key not configured")
        result = _call_openrouter(image_data, config.openrouter_api_key)
    elif provider == "cloudflare":
        if not config.cloudflare_ai_token or not config.cloudflare_account_id:
            raise ValueError("Cloudflare AI token not configured")
        result = _call_cloudflare(image_data, config.cloudflare_ai_token, config.cloudflare_account_id)
    elif provider == "claude":
        if not config.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")
        result = _call_claude(image_data, config.anthropic_api_key)
    elif provider in ("local", "mlx"):
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
    provider: str = "openrouter",
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


def _call_cloudflare(
    image_data: bytes,
    api_token: str,
    account_id: str,
) -> dict[str, Any]:
    """Make Cloudflare Workers AI request for image analysis.

    Args:
        image_data: Image bytes to analyze
        api_token: Cloudflare API token
        account_id: Cloudflare account ID

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    # Encode image to base64 with data URL prefix
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")

    # Detect image type from magic bytes
    if image_data[:4] == b'\xff\xd8\xff\xe0' or image_data[:4] == b'\xff\xd8\xff\xe1':
        media_type = "image/jpeg"
    elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
        media_type = "image/webp"
    elif image_data[:12] == b'\x00\x00\x00\x0cJXL \r\n\x87\n':
        media_type = "image/jxl"
    else:
        media_type = "image/jpeg"  # Default fallback

    image_url = f"data:{media_type};base64,{base64_image}"

    # Build request payload
    payload = {
        "messages": [
            {"role": "system", "content": "You are an image analysis assistant. Always respond with valid JSON."},
            {"role": "user", "content": ANALYSIS_PROMPT},
        ],
        "image": image_url,
    }

    # Make API request
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"Cloudflare AI request failed ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cloudflare AI connection failed: {e.reason}")

    # Extract response text
    if not result.get("success", False):
        errors = result.get("errors", [])
        raise RuntimeError(f"Cloudflare AI error: {errors}")

    response_text = result.get("result", {}).get("response", "")

    # Parse JSON from response
    try:
        if "{" in response_text:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        else:
            return {
                "description": response_text[:100],
                "alt_text": response_text,
                "tags": [],
            }
    except (json.JSONDecodeError, ValueError):
        return {
            "description": "Image analysis completed",
            "alt_text": response_text[:200] if response_text else "No description available",
            "tags": [],
        }


def _call_openrouter(
    image_data: bytes,
    api_key: str,
) -> dict[str, Any]:
    """Make OpenRouter API request for image analysis.

    Uses Claude Haiku 4.5 via OpenRouter's unified API.

    Args:
        image_data: Image bytes to analyze
        api_key: OpenRouter API key

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    # Encode image to base64 with data URL prefix
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")

    # Detect image type from magic bytes
    if image_data[:4] == b'\xff\xd8\xff\xe0' or image_data[:4] == b'\xff\xd8\xff\xe1':
        media_type = "image/jpeg"
    elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
        media_type = "image/webp"
    elif image_data[:12] == b'\x00\x00\x00\x0cJXL \r\n\x87\n':
        media_type = "image/jxl"
    else:
        media_type = "image/jpeg"  # Default fallback

    image_url = f"data:{media_type};base64,{base64_image}"

    # Build request payload (OpenAI-compatible format)
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                        },
                    },
                ],
            }
        ],
    }

    # Make API request
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/AutumnsGrove/CDNUploader",
        "X-Title": "Press CDN Upload CLI",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"OpenRouter request failed ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenRouter connection failed: {e.reason}")

    # Extract response text from OpenAI-compatible format
    try:
        response_text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected OpenRouter response format: {result}")

    # Parse JSON from response
    try:
        if "{" in response_text:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        else:
            return {
                "description": response_text[:100],
                "alt_text": response_text,
                "tags": [],
            }
    except (json.JSONDecodeError, ValueError):
        return {
            "description": "Image analysis completed",
            "alt_text": response_text[:200] if response_text else "No description available",
            "tags": [],
        }


def _call_local(
    image_data: bytes,
    model_name: str = MLX_MODEL_NAME,
) -> dict[str, Any]:
    """Make MLX local model request for image analysis.

    Uses mlx-vlm library to run Qwen VL model locally.

    Args:
        image_data: Image bytes to analyze
        model_name: MLX model name/path to use

    Returns:
        Parsed JSON response with description, alt_text, tags
    """
    try:
        from mlx_vlm import load, generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
    except ImportError:
        raise ImportError(
            "mlx-vlm is not installed. Install it with: pip install mlx-vlm\n"
            "Note: MLX only works on Apple Silicon Macs."
        )

    # Load model from cache or initialize
    if "model" not in _mlx_model_cache or _mlx_model_cache.get("model_name") != model_name:
        _mlx_model_cache["model"], _mlx_model_cache["processor"] = load(model_name)
        _mlx_model_cache["config"] = load_config(model_name)
        _mlx_model_cache["model_name"] = model_name

    model = _mlx_model_cache["model"]
    processor = _mlx_model_cache["processor"]
    config = _mlx_model_cache["config"]

    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(image_data))

    # Ensure image is in RGB mode
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Apply chat template with the analysis prompt
    prompt = apply_chat_template(
        processor,
        config,
        ANALYSIS_PROMPT,
        num_images=1
    )

    # Generate response
    output = generate(
        model,
        processor,
        image,
        prompt,
        max_tokens=1024,
        verbose=False
    )

    # Parse JSON from response
    try:
        # Try to find JSON in response
        if "{" in output:
            start = output.index("{")
            end = output.rindex("}") + 1
            json_str = output[start:end]
            return json.loads(json_str)
        else:
            # If no JSON found, create default response
            return {
                "description": output[:100],
                "alt_text": output,
                "tags": [],
            }
    except (json.JSONDecodeError, ValueError):
        # Fallback for parsing errors
        return {
            "description": "Image analysis completed",
            "alt_text": output[:200] if output else "No description available",
            "tags": [],
        }


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
