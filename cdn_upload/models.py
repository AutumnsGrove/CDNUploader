"""Data models for CDN Upload CLI.

Contains data classes for image metadata, upload results, and processing options.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageMetadata:
    """AI-generated metadata for an image.

    Attributes:
        description: Concise description (max 15 words)
        alt_text: Detailed alt text for accessibility (1-2 sentences)
        tags: List of relevant tags for categorization (3-5 tags)
    """
    description: str
    alt_text: str
    tags: list[str] = field(default_factory=list)


@dataclass
class UploadResult:
    """Result of a successful upload operation.

    Attributes:
        url: CDN URL of the uploaded file
        filename: Final filename on CDN
        hash: First 8 chars of SHA-256 content hash
        size: File size in bytes
        dimensions: Image dimensions as (width, height)
        metadata: Optional AI-generated metadata
    """
    url: str
    filename: str
    hash: str
    size: int
    dimensions: tuple[int, int]
    metadata: Optional[ImageMetadata] = None


@dataclass
class ProcessingOptions:
    """Options for image processing and upload.

    Attributes:
        quality: WebP quality 0-100 (default: 75)
        full_resolution: Keep full resolution, no compression
        analyze: Enable AI analysis for descriptions/tags
        category: Category for organization (default: photos)
        output_format: Output format: plain|markdown|html
        dry_run: Preview without uploading
    """
    quality: int = 75
    full_resolution: bool = False
    analyze: bool = False
    category: str = "photos"
    output_format: str = "plain"
    dry_run: bool = False


@dataclass
class R2Config:
    """Cloudflare R2 configuration.

    Attributes:
        account_id: Cloudflare account ID
        access_key_id: R2 access key ID
        secret_access_key: R2 secret access key
        bucket_name: R2 bucket name
        custom_domain: Custom domain for CDN URLs
        username: Username for CDN path prefix (e.g., autumn -> autumn/2026/01/21/...)
    """
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    custom_domain: str
    username: str


@dataclass
class AIConfig:
    """AI provider configuration.

    Attributes:
        anthropic_api_key: API key for Claude
        openrouter_api_key: API key for OpenRouter (optional)
    """
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
