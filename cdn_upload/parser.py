"""Markdown and HTML parsing for CDN Upload CLI.

Handles document parsing, image reference extraction, link categorization,
and document rewriting with CDN URLs.
"""

import re
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup


# Regex patterns for image extraction
MARKDOWN_IMAGE_PATTERN = re.compile(
    r'!\[.*?\]\((.*?\.(?:jpg|jpeg|png|gif|webp))\)',
    re.IGNORECASE
)
MARKDOWN_HTML_IMG_PATTERN = re.compile(
    r'<img.*?src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']',
    re.IGNORECASE
)
HTML_IMG_PATTERN = re.compile(
    r'<img.*?src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']',
    re.IGNORECASE
)


ReferenceType = Literal["local", "external", "cdn"]


def extract_images(content: str, doc_type: str) -> list[str]:
    """Find all image references in a document.

    Args:
        content: Document content
        doc_type: Document type ('markdown' or 'html')

    Returns:
        List of image paths/URLs found (unique, preserving order)
    """
    images = []
    seen = set()

    if doc_type == 'markdown':
        # Find standard Markdown images: ![alt](path)
        for match in MARKDOWN_IMAGE_PATTERN.finditer(content):
            path = match.group(1)
            if path not in seen:
                images.append(path)
                seen.add(path)

        # Also find HTML img tags embedded in Markdown
        for match in MARKDOWN_HTML_IMG_PATTERN.finditer(content):
            path = match.group(1)
            if path not in seen:
                images.append(path)
                seen.add(path)

    elif doc_type == 'html':
        # Use BeautifulSoup for proper HTML parsing
        soup = BeautifulSoup(content, 'lxml')
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and src not in seen:
                # Check if it's an image file
                if any(src.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    images.append(src)
                    seen.add(src)

    return images


def categorize_reference(ref: str, cdn_domain: str = "cdn.example.com") -> ReferenceType:
    """Determine if a reference is local, external, or already on CDN.

    Args:
        ref: Image reference (path or URL)
        cdn_domain: CDN domain to check against

    Returns:
        Reference type: 'local', 'external', or 'cdn'
    """
    # Already on CDN
    if cdn_domain in ref:
        return "cdn"

    # External URL
    if ref.startswith(('http://', 'https://', '//')):
        return "external"

    # Local file path
    return "local"


def rewrite_document(
    content: str,
    replacements: dict[str, str],
    doc_type: str,
) -> str:
    """Replace image references with CDN URLs.

    Args:
        content: Original document content
        replacements: Mapping of old refs to new CDN URLs
        doc_type: Document type ('markdown' or 'html')

    Returns:
        Document with updated image references
    """
    result = content

    if doc_type == 'markdown':
        # Replace in Markdown image syntax: ![alt](old) -> ![alt](new)
        for old_ref, new_ref in replacements.items():
            # Escape special regex characters in old_ref
            escaped_old = re.escape(old_ref)

            # Replace in ![alt](path) format
            pattern = rf'(!\[.*?\]\(){escaped_old}(\))'
            result = re.sub(pattern, rf'\g<1>{new_ref}\g<2>', result)

            # Also replace in HTML img tags embedded in Markdown
            pattern = rf'(<img.*?src=["\']){escaped_old}(["\'])'
            result = re.sub(pattern, rf'\g<1>{new_ref}\g<2>', result, flags=re.IGNORECASE)

    elif doc_type == 'html':
        # Replace in HTML img src attributes
        for old_ref, new_ref in replacements.items():
            escaped_old = re.escape(old_ref)
            pattern = rf'(<img[^>]*?src=["\']){escaped_old}(["\'])'
            result = re.sub(pattern, rf'\g<1>{new_ref}\g<2>', result, flags=re.IGNORECASE)

    return result


def save_new_document(
    original_path: Path,
    content: str,
) -> Path:
    """Save processed document with _cdn suffix.

    Args:
        original_path: Path to original document
        content: Processed content with CDN URLs

    Returns:
        Path to new document (e.g., document_cdn.md)
    """
    stem = original_path.stem
    suffix = original_path.suffix
    new_name = f"{stem}_cdn{suffix}"
    new_path = original_path.parent / new_name

    with open(new_path, 'w') as f:
        f.write(content)

    return new_path


def resolve_local_path(ref: str, doc_path: Path) -> Path:
    """Resolve a local image reference to an absolute path.

    Args:
        ref: Local image reference (relative or absolute)
        doc_path: Path to the document containing the reference

    Returns:
        Absolute path to the image file
    """
    ref_path = Path(ref)

    if ref_path.is_absolute():
        return ref_path

    # Resolve relative to document location
    return (doc_path.parent / ref_path).resolve()


def detect_document_type(path: Path) -> str:
    """Detect document type from file extension.

    Args:
        path: Path to document

    Returns:
        Document type: 'markdown' or 'html'
    """
    suffix = path.suffix.lower()

    if suffix in {'.md', '.markdown'}:
        return 'markdown'
    elif suffix in {'.html', '.htm'}:
        return 'html'
    else:
        raise ValueError(f"Unsupported document type: {suffix}")
