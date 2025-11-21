"""CDN Upload CLI - Upload images to Cloudflare R2 with automatic optimization.

A fast, intelligent CLI tool for uploading and managing images on your
Cloudflare R2 CDN with automatic WebP conversion, AI analysis, and batch processing.
"""

__version__ = "0.1.0"
__author__ = "CDN Upload CLI"

from .models import ImageMetadata, UploadResult, ProcessingOptions

__all__ = [
    "__version__",
    "ImageMetadata",
    "UploadResult",
    "ProcessingOptions",
]
