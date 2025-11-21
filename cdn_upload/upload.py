"""R2 upload logic and batch handling.

Manages R2 client initialization, single and batch uploads,
duplicate detection, and CDN URL generation.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .models import R2Config, UploadResult, ImageMetadata


def init_r2_client(config: R2Config) -> Any:
    """Create and return a boto3 S3 client configured for R2.

    Args:
        config: R2 configuration with credentials

    Returns:
        Configured boto3 S3 client
    """
    session = boto3.session.Session()
    client = session.client(
        service_name='s3',
        endpoint_url=f'https://{config.account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name='auto'
    )
    return client


def upload_file(
    client: Any,
    bucket: str,
    key: str,
    data: bytes,
    custom_domain: str,
    metadata: dict[str, str] | None = None,
) -> str:
    """Upload a single file to R2 and return CDN URL.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        key: Object key (path in bucket)
        data: File data as bytes
        custom_domain: Custom domain for CDN URL
        metadata: Optional metadata to attach to object

    Returns:
        CDN URL of uploaded file
    """
    # Determine content type based on key extension
    if key.endswith('.webp'):
        content_type = 'image/webp'
    elif key.endswith('.png'):
        content_type = 'image/png'
    elif key.endswith('.jpg') or key.endswith('.jpeg'):
        content_type = 'image/jpeg'
    elif key.endswith('.gif'):
        content_type = 'image/gif'
    else:
        content_type = 'application/octet-stream'

    # Prepare upload parameters
    upload_params = {
        'Bucket': bucket,
        'Key': key,
        'Body': data,
        'ContentType': content_type,
        'CacheControl': 'public, max-age=31536000',  # 1 year cache
    }

    # Add metadata if provided
    if metadata:
        upload_params['Metadata'] = metadata

    # Upload to R2
    client.put_object(**upload_params)

    # Generate CDN URL
    cdn_url = f"https://{custom_domain}/{key}"

    return cdn_url


def delete_file(
    client: Any,
    bucket: str,
    key: str,
) -> bool:
    """Delete a single file from R2.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        key: Object key (path in bucket)

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def batch_delete(
    client: Any,
    bucket: str,
    keys: list[str],
) -> tuple[int, int]:
    """Delete multiple files from R2.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        keys: List of object keys to delete

    Returns:
        Tuple of (deleted_count, failed_count)
    """
    if not keys:
        return (0, 0)

    # S3/R2 delete_objects can handle up to 1000 keys at once
    deleted = 0
    failed = 0

    # Process in batches of 1000
    for i in range(0, len(keys), 1000):
        batch = keys[i:i+1000]
        delete_request = {
            'Objects': [{'Key': key} for key in batch],
            'Quiet': True
        }

        try:
            response = client.delete_objects(Bucket=bucket, Delete=delete_request)
            # Count errors
            errors = response.get('Errors', [])
            failed += len(errors)
            deleted += len(batch) - len(errors)
        except ClientError:
            failed += len(batch)

    return (deleted, failed)


def batch_upload(
    client: Any,
    bucket: str,
    files: list[tuple[str, bytes, dict[str, str] | None]],
    custom_domain: str,
    max_workers: int = 4,
) -> list[str]:
    """Upload multiple files in parallel.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        files: List of (key, data, metadata) tuples
        custom_domain: Custom domain for CDN URLs
        max_workers: Maximum number of parallel uploads

    Returns:
        List of CDN URLs for uploaded files (in same order as input)
    """
    results = [None] * len(files)

    def upload_single(index: int, key: str, data: bytes, metadata: dict[str, str] | None):
        url = upload_file(client, bucket, key, data, custom_domain, metadata)
        return index, url

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, (key, data, metadata) in enumerate(files):
            future = executor.submit(upload_single, i, key, data, metadata)
            futures.append(future)

        for future in as_completed(futures):
            index, url = future.result()
            results[index] = url

    return results


def check_duplicate(
    client: Any,
    bucket: str,
    custom_domain: str,
    category: str,
    date_path: str,
    content_hash: str,
) -> str | None:
    """Check if a file with the same hash already exists.

    Searches for files in the same category/date path that contain
    the content hash in their filename.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        custom_domain: Custom domain for CDN URLs
        category: File category (photos, videos, etc.)
        date_path: Date path (YYYY/MM/DD)
        content_hash: First 8 chars of SHA-256 hash

    Returns:
        Existing CDN URL if duplicate found, None otherwise
    """
    # Search prefix for the date path
    prefix = f"{category}/{date_path}/"

    try:
        # List objects in the date path
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=1000
        )

        # Check if any object contains the hash
        for obj in response.get('Contents', []):
            key = obj['Key']
            # Hash is in the filename like: name_hash.webp or hash.webp
            if content_hash in key:
                return f"https://{custom_domain}/{key}"

        return None

    except ClientError:
        # If there's an error, assume no duplicate
        return None


def list_recent_uploads(
    client: Any,
    bucket: str,
    custom_domain: str,
    limit: int = 10,
    offset: int = 0,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List recent uploads from R2.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name
        custom_domain: Custom domain for CDN URLs
        limit: Number of items per page
        offset: Number of items to skip
        category: Category to filter by (optional)

    Returns:
        List of upload info dictionaries with keys:
        - url: CDN URL
        - key: Object key
        - size: Size in bytes
        - modified: Last modified timestamp
    """
    # Build prefix for filtering
    prefix = f"{category}/" if category else ""

    try:
        # List all objects (R2 doesn't support offset, so we need to fetch more)
        all_objects = []
        continuation_token = None

        while True:
            list_params = {
                'Bucket': bucket,
                'MaxKeys': 1000,
            }
            if prefix:
                list_params['Prefix'] = prefix
            if continuation_token:
                list_params['ContinuationToken'] = continuation_token

            response = client.list_objects_v2(**list_params)

            contents = response.get('Contents', [])
            all_objects.extend(contents)

            if not response.get('IsTruncated', False):
                break
            continuation_token = response.get('NextContinuationToken')

        # Sort by last modified (newest first)
        all_objects.sort(key=lambda x: x['LastModified'], reverse=True)

        # Apply offset and limit
        paginated = all_objects[offset:offset + limit]

        # Format results
        results = []
        for obj in paginated:
            results.append({
                'url': f"https://{custom_domain}/{obj['Key']}",
                'key': obj['Key'],
                'size': obj['Size'],
                'modified': obj['LastModified'],
            })

        return results

    except ClientError as e:
        raise RuntimeError(f"Failed to list uploads: {e}")


def verify_connection(client: Any, bucket: str) -> bool:
    """Verify R2 connection by checking bucket access.

    Args:
        client: Configured boto3 S3 client
        bucket: R2 bucket name

    Returns:
        True if connection successful

    Raises:
        RuntimeError: If connection fails
    """
    try:
        # Try to head the bucket (check if it exists and we have access)
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == '404':
            raise RuntimeError(f"Bucket '{bucket}' not found")
        elif error_code == '403':
            raise RuntimeError(f"Access denied to bucket '{bucket}'. Check your credentials.")
        else:
            raise RuntimeError(f"Failed to connect to R2: {e}")
