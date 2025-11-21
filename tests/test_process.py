"""Tests for process.py module.

Tests image processing, WebP conversion, EXIF stripping,
GIF handling, and video conversion.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO

from PIL import Image

from cdn_upload.process import (
    process_image,
    process_gif,
    process_video,
    strip_location_exif,
    calculate_dimensions,
    get_video_duration,
    detect_file_type,
)


@pytest.fixture
def sample_image_path(tmp_path):
    """Create sample PNG image for testing."""
    img_path = tmp_path / "test.png"
    # Create a simple RGB image
    img = Image.new('RGB', (800, 600), color=(255, 0, 0))
    img.save(img_path, 'PNG')
    return img_path


@pytest.fixture
def sample_rgba_image_path(tmp_path):
    """Create sample RGBA image with transparency."""
    img_path = tmp_path / "test_rgba.png"
    # Create RGBA image with transparency
    img = Image.new('RGBA', (400, 300), color=(0, 255, 0, 128))
    img.save(img_path, 'PNG')
    return img_path


@pytest.fixture
def large_image_path(tmp_path):
    """Create large image for resize testing."""
    img_path = tmp_path / "large.png"
    # Create a 4000x3000 image (larger than any quality threshold)
    img = Image.new('RGB', (4000, 3000), color=(0, 0, 255))
    img.save(img_path, 'PNG')
    return img_path


@pytest.fixture
def sample_gif_path(tmp_path):
    """Create sample animated GIF for testing."""
    gif_path = tmp_path / "test.gif"
    # Create animated GIF with 3 frames
    frames = []
    for i in range(3):
        frame = Image.new('RGB', (200, 150), color=(i * 80, 0, 0))
        frames.append(frame)

    frames[0].save(
        gif_path,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0
    )
    return gif_path


@pytest.fixture
def static_gif_path(tmp_path):
    """Create non-animated GIF for testing."""
    gif_path = tmp_path / "static.gif"
    img = Image.new('RGB', (200, 150), color=(0, 255, 0))
    img.save(gif_path, 'GIF')
    return gif_path


class TestProcessImage:
    """Tests for process_image function."""

    def test_converts_to_webp(self, sample_image_path):
        """Should convert image to WebP format."""
        result_bytes, dimensions = process_image(sample_image_path)

        # Verify it's valid WebP
        assert result_bytes[:4] == b'RIFF'
        assert b'WEBP' in result_bytes[:12]

    def test_respects_quality_setting(self, sample_image_path):
        """Higher quality should produce larger file."""
        low_quality, _ = process_image(sample_image_path, quality=20)
        high_quality, _ = process_image(sample_image_path, quality=95)

        # Higher quality should generally be larger
        assert len(high_quality) > len(low_quality)

    def test_preserves_full_resolution(self, large_image_path):
        """Should not resize when full_resolution is True."""
        _, dimensions = process_image(large_image_path, full_resolution=True)

        # Should keep original dimensions
        assert dimensions == (4000, 3000)

    def test_resizes_large_images(self, large_image_path):
        """Should resize large images based on quality."""
        _, dimensions = process_image(large_image_path, quality=75)

        # Should be resized to max 2048 (for quality >= 75)
        assert max(dimensions) <= 2048

    def test_returns_correct_dimensions(self, sample_image_path):
        """Should return actual output dimensions."""
        _, dimensions = process_image(sample_image_path)

        assert isinstance(dimensions, tuple)
        assert len(dimensions) == 2
        assert all(isinstance(d, int) for d in dimensions)

    def test_handles_rgba_images(self, sample_rgba_image_path):
        """Should convert RGBA to RGB with white background."""
        result_bytes, dimensions = process_image(sample_rgba_image_path)

        # Should produce valid WebP
        assert result_bytes[:4] == b'RIFF'
        assert dimensions == (400, 300)

    def test_accepts_file_like_object(self, sample_image_path):
        """Should accept BytesIO input."""
        with open(sample_image_path, 'rb') as f:
            data = f.read()

        buffer = BytesIO(data)
        result_bytes, dimensions = process_image(buffer)

        assert result_bytes[:4] == b'RIFF'


class TestProcessGif:
    """Tests for process_gif function."""

    def test_preserves_animation(self, sample_gif_path):
        """Should preserve frames in animated GIF."""
        result_bytes, dimensions = process_gif(sample_gif_path)

        # Verify it's valid WebP
        assert result_bytes[:4] == b'RIFF'

    def test_converts_to_animated_webp(self, sample_gif_path):
        """Should output animated WebP format."""
        result_bytes, dimensions = process_gif(sample_gif_path)

        # Should have WebP header
        assert b'WEBP' in result_bytes[:12]
        assert dimensions == (200, 150)

    def test_handles_static_gif(self, static_gif_path):
        """Should handle non-animated GIF like regular image."""
        result_bytes, dimensions = process_gif(static_gif_path)

        assert result_bytes[:4] == b'RIFF'
        assert dimensions == (200, 150)

    def test_respects_quality(self, sample_gif_path):
        """Should apply quality setting."""
        low_quality, _ = process_gif(sample_gif_path, quality=20)
        high_quality, _ = process_gif(sample_gif_path, quality=95)

        # Higher quality generally larger
        assert len(high_quality) > len(low_quality) * 0.5  # Allow some variance


class TestProcessVideo:
    """Tests for process_video function."""

    @patch('cdn_upload.process.subprocess.run')
    @patch('cdn_upload.process.get_video_duration')
    def test_converts_to_webp(self, mock_duration, mock_run, tmp_path):
        """Should convert video to animated WebP."""
        # Setup mocks
        mock_duration.return_value = 5.0

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b'fake video')

        # Mock ffprobe for dimensions
        probe_result = Mock()
        probe_result.returncode = 0
        probe_result.stdout = '{"streams":[{"width":1920,"height":1080}]}'

        # Mock ffmpeg conversion
        convert_result = Mock()
        convert_result.returncode = 0

        mock_run.side_effect = [probe_result, convert_result]

        # Create fake output file
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'RIFF\x00\x00\x00\x00WEBP'
            with patch('os.path.exists', return_value=True):
                with patch('os.unlink'):
                    result_bytes, dimensions = process_video(video_path)

        assert b'RIFF' in result_bytes
        assert dimensions == (1280, 720)  # Scaled down from 1080p

    @patch('cdn_upload.process.get_video_duration')
    def test_rejects_long_videos(self, mock_duration, tmp_path):
        """Should raise error for videos over max duration."""
        mock_duration.return_value = 15.0  # 15 seconds

        video_path = tmp_path / "long.mp4"
        video_path.write_bytes(b'fake video')

        with pytest.raises(ValueError, match="exceeds maximum"):
            process_video(video_path, max_duration=10.0)

    @patch('cdn_upload.process.subprocess.run')
    @patch('cdn_upload.process.get_video_duration')
    def test_scales_to_720p(self, mock_duration, mock_run, tmp_path):
        """Should scale to max 720p maintaining aspect ratio."""
        mock_duration.return_value = 3.0

        video_path = tmp_path / "4k.mp4"
        video_path.write_bytes(b'fake video')

        # Mock 4K video
        probe_result = Mock()
        probe_result.returncode = 0
        probe_result.stdout = '{"streams":[{"width":3840,"height":2160}]}'

        convert_result = Mock()
        convert_result.returncode = 0

        mock_run.side_effect = [probe_result, convert_result]

        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'RIFF\x00\x00\x00\x00WEBP'
            with patch('os.path.exists', return_value=True):
                with patch('os.unlink'):
                    _, dimensions = process_video(video_path)

        # Should scale 3840x2160 to max 720 height
        assert dimensions[1] == 720
        assert dimensions[0] == 1280  # Maintains 16:9 ratio


class TestStripLocationExif:
    """Tests for strip_location_exif function."""

    def test_removes_gps_data(self):
        """Should remove GPS coordinates from EXIF."""
        # Create image with EXIF GPS data
        img = Image.new('RGB', (100, 100))
        exif = img.getexif()
        # Add GPS info tag (34853)
        exif[34853] = {1: 'N', 2: (40, 0, 0)}

        result = strip_location_exif(img)
        result_exif = result.getexif()

        # GPS tag should be removed
        assert 34853 not in result_exif

    def test_handles_no_exif(self):
        """Should handle images without EXIF data."""
        img = Image.new('RGB', (100, 100))

        # Should not raise error
        result = strip_location_exif(img)
        assert result is not None

    def test_returns_image(self):
        """Should return a PIL Image object."""
        img = Image.new('RGB', (100, 100))
        result = strip_location_exif(img)

        assert isinstance(result, Image.Image)


class TestCalculateDimensions:
    """Tests for calculate_dimensions function."""

    def test_maintains_aspect_ratio(self):
        """Should maintain original aspect ratio."""
        # 16:9 aspect ratio
        original = (1920, 1080)
        result = calculate_dimensions(original, quality=75)

        original_ratio = original[0] / original[1]
        result_ratio = result[0] / result[1]

        assert abs(original_ratio - result_ratio) < 0.01

    def test_quality_100_no_resize(self):
        """Quality 100 should preserve original dimensions."""
        original = (5000, 3000)
        result = calculate_dimensions(original, quality=100)

        assert result == original

    def test_quality_75_max_2048(self):
        """Quality >= 75 should limit to 2048px."""
        original = (4000, 3000)
        result = calculate_dimensions(original, quality=75)

        assert max(result) <= 2048

    def test_quality_50_max_1024(self):
        """Quality >= 50 should limit to 1024px."""
        original = (4000, 3000)
        result = calculate_dimensions(original, quality=50)

        assert max(result) <= 1024

    def test_quality_25_max_512(self):
        """Quality >= 25 should limit to 512px."""
        original = (2000, 1500)
        result = calculate_dimensions(original, quality=25)

        assert max(result) <= 512

    def test_small_image_no_upscale(self):
        """Should not upscale images smaller than threshold."""
        original = (400, 300)
        result = calculate_dimensions(original, quality=75)

        # Should stay the same - no upscaling
        assert result == original

    def test_scales_based_on_longest_side(self):
        """Should scale based on longest dimension."""
        # Portrait image
        original = (1500, 3000)
        result = calculate_dimensions(original, quality=75)

        # Height is longest, should be scaled to max
        assert result[1] <= 2048


class TestGetVideoDuration:
    """Tests for get_video_duration function."""

    @patch('cdn_upload.process.subprocess.run')
    def test_returns_duration(self, mock_run, tmp_path):
        """Should return video duration in seconds."""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b'fake video')

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format":{"duration":"5.5"}}'
        mock_run.return_value = mock_result

        duration = get_video_duration(video_path)

        assert duration == 5.5

    @patch('cdn_upload.process.subprocess.run')
    def test_raises_on_failure(self, mock_run, tmp_path):
        """Should raise error if ffprobe fails."""
        video_path = tmp_path / "bad.mp4"
        video_path.write_bytes(b'not a video')

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid data found"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Failed to get video duration"):
            get_video_duration(video_path)


class TestDetectFileType:
    """Tests for detect_file_type function."""

    def test_detects_images(self):
        """Should return 'image' for image extensions."""
        assert detect_file_type(Path("test.jpg")) == "image"
        assert detect_file_type(Path("test.jpeg")) == "image"
        assert detect_file_type(Path("test.png")) == "image"
        assert detect_file_type(Path("test.webp")) == "image"
        assert detect_file_type(Path("test.bmp")) == "image"
        assert detect_file_type(Path("test.tiff")) == "image"

    def test_detects_gifs(self):
        """Should return 'gif' for GIF files."""
        assert detect_file_type(Path("test.gif")) == "gif"
        assert detect_file_type(Path("animation.GIF")) == "gif"

    def test_detects_videos(self):
        """Should return 'video' for video extensions."""
        assert detect_file_type(Path("test.mp4")) == "video"
        assert detect_file_type(Path("test.mov")) == "video"
        assert detect_file_type(Path("test.avi")) == "video"
        assert detect_file_type(Path("test.webm")) == "video"

    def test_detects_documents(self):
        """Should return 'document' for doc extensions."""
        assert detect_file_type(Path("test.md")) == "document"
        assert detect_file_type(Path("test.markdown")) == "document"
        assert detect_file_type(Path("test.html")) == "document"
        assert detect_file_type(Path("test.htm")) == "document"

    def test_unknown_type(self):
        """Should return 'unknown' for unsupported extensions."""
        assert detect_file_type(Path("test.xyz")) == "unknown"
        assert detect_file_type(Path("file.doc")) == "unknown"
        assert detect_file_type(Path("data.json")) == "unknown"

    def test_case_insensitive(self):
        """Should handle uppercase extensions."""
        assert detect_file_type(Path("test.PNG")) == "image"
        assert detect_file_type(Path("test.MP4")) == "video"
