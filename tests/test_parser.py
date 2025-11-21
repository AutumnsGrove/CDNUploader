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
        # TODO: Implement test
        pass

    def test_extracts_html_images_in_markdown(self):
        """Should find <img src> in markdown files."""
        # TODO: Implement test
        pass

    def test_extracts_html_images(self):
        """Should find <img src> in HTML files."""
        # TODO: Implement test
        pass

    def test_ignores_non_image_links(self):
        """Should not extract links to non-image files."""
        # TODO: Implement test
        pass


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


class TestRewriteDocument:
    """Tests for rewrite_document function."""

    def test_replaces_image_refs(self):
        """Should replace local refs with CDN URLs."""
        # TODO: Implement test
        pass

    def test_preserves_non_replaced_content(self):
        """Should not modify content without replacements."""
        # TODO: Implement test
        pass


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
