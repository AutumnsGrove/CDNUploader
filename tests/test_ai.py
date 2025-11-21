"""Tests for ai.py module.

Tests AI analysis, caching, Claude API integration, and batch processing.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

from cdn_upload.ai import (
    analyze_image,
    batch_analyze,
    _call_claude,
    load_cache,
    save_cache,
    get_cached_analysis,
    cache_analysis,
)
from cdn_upload.models import ImageMetadata, AIConfig


@pytest.fixture
def ai_config():
    """Sample AI configuration for testing."""
    return AIConfig(
        anthropic_api_key="test_api_key",
        openrouter_api_key=None,
    )


@pytest.fixture
def sample_image_data():
    """Sample image bytes for testing."""
    return b'\x00\x01\x02\x03\x04\x05'


@pytest.fixture
def cache_dir(tmp_path):
    """Temporary cache directory."""
    return tmp_path / "cache"


class TestAnalyzeImage:
    """Tests for analyze_image function."""

    @patch('cdn_upload.ai._call_claude')
    def test_calls_claude_with_image_data(self, mock_call, ai_config, sample_image_data):
        """Should call Claude API with image data."""
        mock_call.return_value = {
            "description": "Test image",
            "alt_text": "A test image for testing",
            "tags": ["test", "image"]
        }

        result = analyze_image(sample_image_data, ai_config, provider="claude")

        mock_call.assert_called_once_with(sample_image_data, "test_api_key")
        assert result.description == "Test image"
        assert result.alt_text == "A test image for testing"
        assert result.tags == ["test", "image"]

    @patch('cdn_upload.ai.get_cached_analysis')
    def test_returns_cached_result(self, mock_cache, ai_config, sample_image_data):
        """Should return cached result if available."""
        cached_metadata = ImageMetadata(
            description="Cached",
            alt_text="Cached result",
            tags=["cached"]
        )
        mock_cache.return_value = cached_metadata

        result = analyze_image(
            sample_image_data,
            ai_config,
            content_hash="abc123",
            provider="claude"
        )

        assert result == cached_metadata

    @patch('cdn_upload.ai._call_claude')
    @patch('cdn_upload.ai.cache_analysis')
    @patch('cdn_upload.ai.get_cached_analysis')
    def test_caches_new_result(self, mock_get, mock_save, mock_call, ai_config, sample_image_data):
        """Should cache result when hash provided."""
        mock_get.return_value = None
        mock_call.return_value = {
            "description": "New",
            "alt_text": "New result",
            "tags": ["new"]
        }

        result = analyze_image(
            sample_image_data,
            ai_config,
            content_hash="abc123",
            provider="claude"
        )

        mock_save.assert_called_once()
        call_args = mock_save.call_args[0]
        assert call_args[0] == "abc123"
        assert call_args[1].description == "New"

    def test_raises_on_missing_api_key(self, sample_image_data):
        """Should raise error when API key missing."""
        config = AIConfig(anthropic_api_key=None, openrouter_api_key=None)

        with pytest.raises(ValueError, match="API key not configured"):
            analyze_image(sample_image_data, config, provider="claude")

    def test_raises_on_unknown_provider(self, ai_config, sample_image_data):
        """Should raise error for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            analyze_image(sample_image_data, ai_config, provider="unknown")


class TestBatchAnalyze:
    """Tests for batch_analyze function."""

    @patch('cdn_upload.ai.analyze_image')
    @patch('cdn_upload.ai.get_cached_analysis')
    def test_processes_multiple_images(self, mock_cache, mock_analyze, ai_config):
        """Should process all images in batch."""
        mock_cache.return_value = None
        mock_analyze.side_effect = [
            ImageMetadata("Desc1", "Alt1", ["tag1"]),
            ImageMetadata("Desc2", "Alt2", ["tag2"]),
        ]

        images = [
            ("hash1", b"data1"),
            ("hash2", b"data2"),
        ]

        results = batch_analyze(images, ai_config)

        assert len(results) == 2
        assert "hash1" in results
        assert "hash2" in results

    @patch('cdn_upload.ai.get_cached_analysis')
    def test_uses_cache_for_known_images(self, mock_cache, ai_config):
        """Should return cached results without API call."""
        cached = ImageMetadata("Cached", "Cached alt", ["cached"])
        mock_cache.return_value = cached

        images = [
            ("hash1", b"data1"),
        ]

        results = batch_analyze(images, ai_config)

        assert results["hash1"] == cached

    @patch('cdn_upload.ai.analyze_image')
    @patch('cdn_upload.ai.get_cached_analysis')
    def test_handles_empty_list(self, mock_cache, mock_analyze, ai_config):
        """Should handle empty image list."""
        results = batch_analyze([], ai_config)

        assert results == {}
        mock_analyze.assert_not_called()


class TestCallClaude:
    """Tests for _call_claude function."""

    @patch('cdn_upload.ai.anthropic.Anthropic')
    def test_calls_api_with_correct_format(self, mock_anthropic):
        """Should call API with base64 encoded image."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"description": "Test", "alt_text": "Test alt", "tags": ["tag"]}')]
        mock_client.messages.create.return_value = mock_message

        result = _call_claude(b"image data", "api_key")

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert "image" in str(call_kwargs["messages"])

    @patch('cdn_upload.ai.anthropic.Anthropic')
    def test_parses_json_response(self, mock_anthropic):
        """Should parse JSON from response."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        json_response = '{"description": "A sunset", "alt_text": "Beautiful sunset over ocean", "tags": ["sunset", "ocean"]}'
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json_response)]
        mock_client.messages.create.return_value = mock_message

        result = _call_claude(b"image", "key")

        assert result["description"] == "A sunset"
        assert result["alt_text"] == "Beautiful sunset over ocean"
        assert result["tags"] == ["sunset", "ocean"]

    @patch('cdn_upload.ai.anthropic.Anthropic')
    def test_handles_json_in_text(self, mock_anthropic):
        """Should extract JSON from text response."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        text_response = 'Here is the analysis:\n{"description": "Test", "alt_text": "Alt", "tags": ["t"]}\nDone.'
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=text_response)]
        mock_client.messages.create.return_value = mock_message

        result = _call_claude(b"image", "key")

        assert result["description"] == "Test"

    @patch('cdn_upload.ai.anthropic.Anthropic')
    def test_handles_malformed_json(self, mock_anthropic):
        """Should handle malformed JSON gracefully."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        bad_response = 'This is not JSON at all'
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=bad_response)]
        mock_client.messages.create.return_value = mock_message

        result = _call_claude(b"image", "key")

        # Should return fallback response
        assert "description" in result
        assert "alt_text" in result


class TestCacheFunctions:
    """Tests for cache management functions."""

    @patch('cdn_upload.ai.get_cache_dir')
    def test_load_cache_returns_empty_when_missing(self, mock_cache_dir, tmp_path):
        """Should return empty dict when cache file doesn't exist."""
        mock_cache_dir.return_value = tmp_path

        result = load_cache()

        assert result == {}

    @patch('cdn_upload.ai.get_cache_dir')
    def test_load_cache_reads_file(self, mock_cache_dir, tmp_path):
        """Should read cache from file."""
        mock_cache_dir.return_value = tmp_path

        cache_file = tmp_path / "analysis.json"
        cache_data = {"hash1": {"description": "Test", "alt_text": "Alt", "tags": []}}
        cache_file.write_text(json.dumps(cache_data))

        result = load_cache()

        assert result == cache_data

    @patch('cdn_upload.ai.get_cache_dir')
    def test_save_cache_writes_file(self, mock_cache_dir, tmp_path):
        """Should write cache to file."""
        mock_cache_dir.return_value = tmp_path

        cache_data = {"hash1": {"description": "Test", "alt_text": "Alt", "tags": []}}
        save_cache(cache_data)

        cache_file = tmp_path / "analysis.json"
        assert cache_file.exists()

        loaded = json.loads(cache_file.read_text())
        assert loaded == cache_data

    @patch('cdn_upload.ai.load_cache')
    def test_get_cached_analysis_found(self, mock_load):
        """Should return ImageMetadata when found in cache."""
        mock_load.return_value = {
            "abc123": {
                "description": "Cached desc",
                "alt_text": "Cached alt",
                "tags": ["cached"]
            }
        }

        result = get_cached_analysis("abc123")

        assert result is not None
        assert result.description == "Cached desc"
        assert result.alt_text == "Cached alt"
        assert result.tags == ["cached"]

    @patch('cdn_upload.ai.load_cache')
    def test_get_cached_analysis_not_found(self, mock_load):
        """Should return None when not in cache."""
        mock_load.return_value = {}

        result = get_cached_analysis("missing")

        assert result is None

    @patch('cdn_upload.ai.save_cache')
    @patch('cdn_upload.ai.load_cache')
    def test_cache_analysis_saves(self, mock_load, mock_save):
        """Should save analysis to cache."""
        mock_load.return_value = {}

        metadata = ImageMetadata("Desc", "Alt", ["tag"])
        cache_analysis("abc123", metadata)

        mock_save.assert_called_once()
        saved_cache = mock_save.call_args[0][0]
        assert "abc123" in saved_cache
        assert saved_cache["abc123"]["description"] == "Desc"
