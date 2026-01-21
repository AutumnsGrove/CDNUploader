"""Tests for upload.py module.

Tests R2 client initialization, upload operations, duplicate detection,
and batch upload functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call

from botocore.exceptions import ClientError

from cdn_upload.upload import (
    init_r2_client,
    upload_file,
    batch_upload,
    check_duplicate,
    list_recent_uploads,
    verify_connection,
)
from cdn_upload.models import R2Config


@pytest.fixture
def r2_config():
    """Sample R2 configuration for testing."""
    return R2Config(
        account_id="test_account",
        access_key_id="test_key",
        secret_access_key="test_secret",
        bucket_name="test_bucket",
        custom_domain="cdn.test.com",
        username="testuser",
    )


@pytest.fixture
def mock_client():
    """Mock boto3 S3 client."""
    return MagicMock()


class TestInitR2Client:
    """Tests for init_r2_client function."""

    @patch('cdn_upload.upload.boto3.session.Session')
    def test_creates_client_with_correct_endpoint(self, mock_session, r2_config):
        """Should create client with correct R2 endpoint."""
        mock_client_instance = MagicMock()
        mock_session.return_value.client.return_value = mock_client_instance

        client = init_r2_client(r2_config)

        mock_session.return_value.client.assert_called_once()
        call_kwargs = mock_session.return_value.client.call_args[1]

        assert call_kwargs['endpoint_url'] == 'https://test_account.r2.cloudflarestorage.com'
        assert call_kwargs['service_name'] == 's3'

    @patch('cdn_upload.upload.boto3.session.Session')
    def test_uses_provided_credentials(self, mock_session, r2_config):
        """Should use credentials from config."""
        mock_client_instance = MagicMock()
        mock_session.return_value.client.return_value = mock_client_instance

        init_r2_client(r2_config)

        call_kwargs = mock_session.return_value.client.call_args[1]
        assert call_kwargs['aws_access_key_id'] == 'test_key'
        assert call_kwargs['aws_secret_access_key'] == 'test_secret'

    @patch('cdn_upload.upload.boto3.session.Session')
    def test_returns_client(self, mock_session, r2_config):
        """Should return the created client."""
        mock_client_instance = MagicMock()
        mock_session.return_value.client.return_value = mock_client_instance

        result = init_r2_client(r2_config)

        assert result == mock_client_instance


class TestUploadFile:
    """Tests for upload_file function."""

    def test_uploads_file_to_bucket(self, mock_client):
        """Should upload file data to specified bucket/key."""
        data = b'test file content'
        url = upload_file(
            mock_client,
            'test_bucket',
            'photos/2024/01/15/image.webp',
            data,
            'cdn.test.com'
        )

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['Bucket'] == 'test_bucket'
        assert call_kwargs['Key'] == 'photos/2024/01/15/image.webp'
        assert call_kwargs['Body'] == data

    def test_sets_correct_content_type_webp(self, mock_client):
        """Should set content type to image/webp for WebP files."""
        upload_file(mock_client, 'bucket', 'test.webp', b'data', 'cdn.test.com')

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['ContentType'] == 'image/webp'

    def test_sets_correct_content_type_png(self, mock_client):
        """Should set content type to image/png for PNG files."""
        upload_file(mock_client, 'bucket', 'test.png', b'data', 'cdn.test.com')

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['ContentType'] == 'image/png'

    def test_sets_correct_content_type_jpeg(self, mock_client):
        """Should set content type for JPEG files."""
        upload_file(mock_client, 'bucket', 'test.jpg', b'data', 'cdn.test.com')
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['ContentType'] == 'image/jpeg'

        upload_file(mock_client, 'bucket', 'test.jpeg', b'data', 'cdn.test.com')
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['ContentType'] == 'image/jpeg'

    def test_sets_cache_control_header(self, mock_client):
        """Should set 1-year cache control."""
        upload_file(mock_client, 'bucket', 'test.webp', b'data', 'cdn.test.com')

        call_kwargs = mock_client.put_object.call_args[1]
        assert 'max-age=31536000' in call_kwargs['CacheControl']

    def test_returns_cdn_url(self, mock_client):
        """Should return correct CDN URL."""
        url = upload_file(
            mock_client,
            'bucket',
            'photos/2024/01/15/image.webp',
            b'data',
            'cdn.example.com'
        )

        assert url == 'https://cdn.example.com/photos/2024/01/15/image.webp'

    def test_includes_metadata_when_provided(self, mock_client):
        """Should include metadata in upload."""
        metadata = {'description': 'test image', 'tags': 'photo,test'}
        upload_file(mock_client, 'bucket', 'test.webp', b'data', 'cdn.test.com', metadata)

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs['Metadata'] == metadata

    def test_omits_metadata_when_none(self, mock_client):
        """Should not include Metadata key when None."""
        upload_file(mock_client, 'bucket', 'test.webp', b'data', 'cdn.test.com', None)

        call_kwargs = mock_client.put_object.call_args[1]
        assert 'Metadata' not in call_kwargs


class TestBatchUpload:
    """Tests for batch_upload function."""

    def test_uploads_multiple_files(self, mock_client):
        """Should upload all files in batch."""
        files = [
            ('key1.webp', b'data1', None),
            ('key2.webp', b'data2', None),
            ('key3.webp', b'data3', None),
        ]

        batch_upload(mock_client, 'bucket', files, 'cdn.test.com')

        assert mock_client.put_object.call_count == 3

    def test_returns_all_urls(self, mock_client):
        """Should return URLs for all uploaded files."""
        files = [
            ('key1.webp', b'data1', None),
            ('key2.webp', b'data2', None),
        ]

        urls = batch_upload(mock_client, 'bucket', files, 'cdn.test.com')

        assert len(urls) == 2
        assert 'https://cdn.test.com/key1.webp' in urls
        assert 'https://cdn.test.com/key2.webp' in urls

    def test_preserves_order(self, mock_client):
        """Should return URLs in same order as input files."""
        files = [
            ('first.webp', b'data1', None),
            ('second.webp', b'data2', None),
            ('third.webp', b'data3', None),
        ]

        urls = batch_upload(mock_client, 'bucket', files, 'cdn.test.com')

        assert urls[0] == 'https://cdn.test.com/first.webp'
        assert urls[1] == 'https://cdn.test.com/second.webp'
        assert urls[2] == 'https://cdn.test.com/third.webp'

    def test_handles_empty_list(self, mock_client):
        """Should handle empty file list."""
        urls = batch_upload(mock_client, 'bucket', [], 'cdn.test.com')

        assert urls == []
        mock_client.put_object.assert_not_called()


class TestCheckDuplicate:
    """Tests for check_duplicate function."""

    def test_finds_existing_file(self, mock_client):
        """Should return URL if file with hash exists."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'photos/2024/01/15/sunset_abc12345.webp'},
            ]
        }

        result = check_duplicate(
            mock_client,
            'bucket',
            'cdn.test.com',
            'photos',
            '2024/01/15',
            'abc12345'
        )

        assert result == 'https://cdn.test.com/photos/2024/01/15/sunset_abc12345.webp'

    def test_returns_none_for_new_file(self, mock_client):
        """Should return None if no matching hash found."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'photos/2024/01/15/other_xyz99999.webp'},
            ]
        }

        result = check_duplicate(
            mock_client,
            'bucket',
            'cdn.test.com',
            'photos',
            '2024/01/15',
            'abc12345'
        )

        assert result is None

    def test_returns_none_for_empty_bucket(self, mock_client):
        """Should return None if bucket path is empty."""
        mock_client.list_objects_v2.return_value = {'Contents': []}

        result = check_duplicate(
            mock_client,
            'bucket',
            'cdn.test.com',
            'photos',
            '2024/01/15',
            'abc12345'
        )

        assert result is None

    def test_handles_client_error(self, mock_client):
        """Should return None on client error."""
        mock_client.list_objects_v2.side_effect = ClientError(
            {'Error': {'Code': '500', 'Message': 'Internal Error'}},
            'ListObjects'
        )

        result = check_duplicate(
            mock_client,
            'bucket',
            'cdn.test.com',
            'photos',
            '2024/01/15',
            'abc12345'
        )

        assert result is None


class TestListRecentUploads:
    """Tests for list_recent_uploads function."""

    def test_returns_correct_page(self, mock_client):
        """Should return requested page of results."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': f'photos/img{i}.webp', 'Size': 1000, 'LastModified': datetime(2024, 1, 20 - i)}
                for i in range(20)
            ],
            'IsTruncated': False,
        }

        results = list_recent_uploads(
            mock_client,
            'bucket',
            'cdn.test.com',
            limit=5,
            offset=0
        )

        assert len(results) == 5

    def test_sorts_by_most_recent(self, mock_client):
        """Should sort results by LastModified descending."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'old.webp', 'Size': 100, 'LastModified': datetime(2024, 1, 1)},
                {'Key': 'new.webp', 'Size': 100, 'LastModified': datetime(2024, 1, 15)},
                {'Key': 'mid.webp', 'Size': 100, 'LastModified': datetime(2024, 1, 8)},
            ],
            'IsTruncated': False,
        }

        results = list_recent_uploads(mock_client, 'bucket', 'cdn.test.com')

        assert results[0]['key'] == 'new.webp'
        assert results[1]['key'] == 'mid.webp'
        assert results[2]['key'] == 'old.webp'

    def test_applies_offset(self, mock_client):
        """Should skip items based on offset."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': f'img{i}.webp', 'Size': 100, 'LastModified': datetime(2024, 1, 15 - i)}
                for i in range(10)
            ],
            'IsTruncated': False,
        }

        results = list_recent_uploads(
            mock_client,
            'bucket',
            'cdn.test.com',
            limit=3,
            offset=5
        )

        assert len(results) == 3

    def test_filters_by_category(self, mock_client):
        """Should filter by category prefix."""
        mock_client.list_objects_v2.return_value = {
            'Contents': [],
            'IsTruncated': False,
        }

        list_recent_uploads(
            mock_client,
            'bucket',
            'cdn.test.com',
            category='photos'
        )

        call_kwargs = mock_client.list_objects_v2.call_args[1]
        assert call_kwargs['Prefix'] == 'photos/'

    def test_returns_formatted_results(self, mock_client):
        """Should return properly formatted result dictionaries."""
        modified_time = datetime(2024, 1, 15, 10, 30, 0)
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'photos/test.webp', 'Size': 1234, 'LastModified': modified_time},
            ],
            'IsTruncated': False,
        }

        results = list_recent_uploads(mock_client, 'bucket', 'cdn.test.com')

        assert len(results) == 1
        assert results[0]['url'] == 'https://cdn.test.com/photos/test.webp'
        assert results[0]['key'] == 'photos/test.webp'
        assert results[0]['size'] == 1234
        assert results[0]['modified'] == modified_time

    def test_raises_on_client_error(self, mock_client):
        """Should raise RuntimeError on client error."""
        mock_client.list_objects_v2.side_effect = ClientError(
            {'Error': {'Code': '500', 'Message': 'Internal Error'}},
            'ListObjects'
        )

        with pytest.raises(RuntimeError, match="Failed to list uploads"):
            list_recent_uploads(mock_client, 'bucket', 'cdn.test.com')


class TestVerifyConnection:
    """Tests for verify_connection function."""

    def test_returns_true_on_success(self, mock_client):
        """Should return True when bucket is accessible."""
        mock_client.head_bucket.return_value = {}

        result = verify_connection(mock_client, 'test_bucket')

        assert result is True
        mock_client.head_bucket.assert_called_once_with(Bucket='test_bucket')

    def test_raises_on_not_found(self, mock_client):
        """Should raise error when bucket not found."""
        mock_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': '404', 'Message': 'Not Found'}},
            'HeadBucket'
        )

        with pytest.raises(RuntimeError, match="not found"):
            verify_connection(mock_client, 'missing_bucket')

    def test_raises_on_access_denied(self, mock_client):
        """Should raise error when access denied."""
        mock_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': '403', 'Message': 'Forbidden'}},
            'HeadBucket'
        )

        with pytest.raises(RuntimeError, match="Access denied"):
            verify_connection(mock_client, 'private_bucket')

    def test_raises_on_other_error(self, mock_client):
        """Should raise error for other client errors."""
        mock_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': '500', 'Message': 'Internal Error'}},
            'HeadBucket'
        )

        with pytest.raises(RuntimeError, match="Failed to connect"):
            verify_connection(mock_client, 'bucket')
