"""Tests for parser.py module.

Tests document parsing, image extraction, link categorization,
and document rewriting.
"""

import pytest
from pathlib import Path

from cdn_upload.parser import (
    extract_images,
    categorize_reference,
    rewrite_document,
    save_new_document,
    resolve_local_path,
    detect_document_type,
)


class TestExtractImages:
    """Tests for extract_images function."""

    def test_extracts_markdown_images(self):
        """Should find ![alt](path.jpg) syntax."""
        content = """
# My Post

Here is an image:
![Alt text](images/photo.jpg)

And another:
![](./screenshot.png)
"""
        images = extract_images(content, 'markdown')

        assert len(images) == 2
        assert 'images/photo.jpg' in images
        assert './screenshot.png' in images

    def test_extracts_html_images_in_markdown(self):
        """Should find <img src> in markdown files."""
        content = """
# My Post

<img src="images/logo.png" alt="Logo">

Some text here.

<img src='assets/banner.webp'>
"""
        images = extract_images(content, 'markdown')

        assert len(images) == 2
        assert 'images/logo.png' in images
        assert 'assets/banner.webp' in images

    def test_extracts_html_images(self):
        """Should find <img src> in HTML files."""
        content = """
<!DOCTYPE html>
<html>
<body>
    <img src="images/hero.jpg" alt="Hero">
    <div>
        <img src='gallery/photo1.png'>
    </div>
</body>
</html>
"""
        images = extract_images(content, 'html')

        assert len(images) == 2
        assert 'images/hero.jpg' in images
        assert 'gallery/photo1.png' in images

    def test_ignores_non_image_links(self):
        """Should not extract links to non-image files."""
        content = """
# My Post

![PDF doc](document.pdf)
[Link](page.html)
![Image](real.jpg)
"""
        images = extract_images(content, 'markdown')

        # Should only find the real image
        assert len(images) == 1
        assert 'real.jpg' in images

    def test_deduplicates_images(self):
        """Should return unique images only."""
        content = """
![First](image.jpg)
![Second](image.jpg)
![Different](other.png)
"""
        images = extract_images(content, 'markdown')

        assert len(images) == 2
        assert images.count('image.jpg') == 1

    def test_handles_various_extensions(self):
        """Should handle all supported image extensions."""
        content = """
![](a.jpg)
![](b.jpeg)
![](c.png)
![](d.gif)
![](e.webp)
![](f.JPG)
"""
        images = extract_images(content, 'markdown')

        assert len(images) == 6


class TestCategorizeReference:
    """Tests for categorize_reference function."""

    def test_identifies_cdn_urls(self):
        """Should return 'cdn' for CDN domain URLs."""
        ref = "https://cdn.autumnsgrove.com/photos/test.webp"
        assert categorize_reference(ref) == "cdn"

    def test_identifies_external_urls(self):
        """Should return 'external' for non-CDN URLs."""
        ref = "https://example.com/image.jpg"
        assert categorize_reference(ref) == "external"

    def test_identifies_local_paths(self):
        """Should return 'local' for file paths."""
        assert categorize_reference("images/photo.jpg") == "local"
        assert categorize_reference("./photo.jpg") == "local"
        assert categorize_reference("../assets/photo.jpg") == "local"

    def test_custom_cdn_domain(self):
        """Should work with custom CDN domain."""
        ref = "https://mycdn.example.com/image.webp"
        assert categorize_reference(ref, "mycdn.example.com") == "cdn"

    def test_protocol_relative_urls(self):
        """Should treat protocol-relative URLs as external."""
        assert categorize_reference("//example.com/image.jpg") == "external"


class TestRewriteDocument:
    """Tests for rewrite_document function."""

    def test_replaces_markdown_image_refs(self):
        """Should replace local refs with CDN URLs in Markdown."""
        content = "![Alt](images/photo.jpg)"
        replacements = {"images/photo.jpg": "https://cdn.example.com/photo.webp"}

        result = rewrite_document(content, replacements, 'markdown')

        assert "https://cdn.example.com/photo.webp" in result
        assert "images/photo.jpg" not in result

    def test_replaces_html_img_refs(self):
        """Should replace refs in HTML img tags."""
        content = '<img src="images/photo.jpg" alt="Photo">'
        replacements = {"images/photo.jpg": "https://cdn.example.com/photo.webp"}

        result = rewrite_document(content, replacements, 'html')

        assert 'src="https://cdn.example.com/photo.webp"' in result

    def test_preserves_non_replaced_content(self):
        """Should not modify content without replacements."""
        content = "![Alt](keep.jpg)\n\nSome text here."
        replacements = {"other.jpg": "https://cdn.example.com/other.webp"}

        result = rewrite_document(content, replacements, 'markdown')

        assert result == content

    def test_replaces_multiple_refs(self):
        """Should replace multiple references."""
        content = "![A](a.jpg) and ![B](b.png)"
        replacements = {
            "a.jpg": "https://cdn.example.com/a.webp",
            "b.png": "https://cdn.example.com/b.webp"
        }

        result = rewrite_document(content, replacements, 'markdown')

        assert "https://cdn.example.com/a.webp" in result
        assert "https://cdn.example.com/b.webp" in result

    def test_handles_special_characters(self):
        """Should handle paths with special regex characters."""
        content = "![Alt](images/photo (1).jpg)"
        replacements = {"images/photo (1).jpg": "https://cdn.example.com/photo.webp"}

        result = rewrite_document(content, replacements, 'markdown')

        assert "https://cdn.example.com/photo.webp" in result

    def test_preserves_alt_text(self):
        """Should preserve alt text in Markdown."""
        content = "![My Important Alt Text](image.jpg)"
        replacements = {"image.jpg": "https://cdn.example.com/image.webp"}

        result = rewrite_document(content, replacements, 'markdown')

        assert "![My Important Alt Text]" in result


class TestSaveNewDocument:
    """Tests for save_new_document function."""

    def test_creates_cdn_suffix_file(self, tmp_path):
        """Should create file with _cdn suffix."""
        original = tmp_path / "test.md"
        original.write_text("# Test")

        result = save_new_document(original, "# Updated")

        assert result.name == "test_cdn.md"
        assert result.exists()
        assert result.read_text() == "# Updated"

    def test_preserves_extension(self, tmp_path):
        """Should preserve original file extension."""
        original = tmp_path / "test.html"
        original.write_text("<html></html>")

        result = save_new_document(original, "<html>updated</html>")

        assert result.suffix == ".html"

    def test_creates_in_same_directory(self, tmp_path):
        """Should create new file in same directory as original."""
        subdir = tmp_path / "docs"
        subdir.mkdir()
        original = subdir / "post.md"
        original.write_text("content")

        result = save_new_document(original, "new content")

        assert result.parent == subdir


class TestResolveLocalPath:
    """Tests for resolve_local_path function."""

    def test_resolves_relative_path(self, tmp_path):
        """Should resolve path relative to document."""
        doc_path = tmp_path / "blog" / "post.md"
        doc_path.parent.mkdir(parents=True)
        doc_path.touch()

        result = resolve_local_path("../images/photo.jpg", doc_path)

        expected = (tmp_path / "images" / "photo.jpg").resolve()
        assert result == expected

    def test_handles_absolute_path(self, tmp_path):
        """Should return absolute paths unchanged."""
        doc_path = tmp_path / "post.md"
        abs_path = "/var/images/photo.jpg"

        result = resolve_local_path(abs_path, doc_path)

        assert result == Path(abs_path)

    def test_resolves_same_directory(self, tmp_path):
        """Should resolve paths in same directory."""
        doc_path = tmp_path / "post.md"
        doc_path.touch()

        result = resolve_local_path("image.jpg", doc_path)

        expected = (tmp_path / "image.jpg").resolve()
        assert result == expected


class TestDetectDocumentType:
    """Tests for detect_document_type function."""

    def test_detects_markdown(self):
        """Should return 'markdown' for .md files."""
        assert detect_document_type(Path("test.md")) == "markdown"
        assert detect_document_type(Path("test.markdown")) == "markdown"

    def test_detects_html(self):
        """Should return 'html' for .html files."""
        assert detect_document_type(Path("test.html")) == "html"
        assert detect_document_type(Path("test.htm")) == "html"

    def test_raises_for_unsupported(self):
        """Should raise ValueError for unsupported types."""
        with pytest.raises(ValueError):
            detect_document_type(Path("test.txt"))

    def test_case_insensitive(self):
        """Should handle uppercase extensions."""
        assert detect_document_type(Path("test.MD")) == "markdown"
        assert detect_document_type(Path("test.HTML")) == "html"
