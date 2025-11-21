# CDN Upload CLI - Implementation Specification

## Overview

CLI tool for uploading images to Cloudflare R2 CDN with automatic WebP conversion, optional AI analysis, and intelligent file management.

## Core Architecture

```
cdn-upload/
├── cdn_upload/
│   ├── __init__.py
│   ├── cli.py              # Main CLI interface (typer)
│   ├── upload.py           # Upload logic and R2 interaction
│   ├── process.py          # Image/video processing (Pillow, ffmpeg)
│   ├── ai.py               # AI analysis (Claude, OpenRouter, local)
│   ├── parser.py           # Markdown/HTML parsing and link extraction
│   ├── storage.py          # Hash calculation, duplicate detection
│   ├── config.py           # Load secrets.json, manage config
│   ├── utils.py            # Helpers (clipboard, formatting)
│   └── models.py           # Data models (ImageMetadata, etc)
├── secrets.json.template
├── pyproject.toml
└── README.md
```

## File Naming Convention

### With AI Analysis
```
photos/2025/03/16/photo_of_Sunset_Beach_a3f9b2c1.webp
<category>/<year>/<month>/<day>/<ai_description>_<hash>.webp
```

### Without AI Analysis
```
photos/2025/03/16/a3f9b2c1_original_filename.webp
<category>/<year>/<month>/<day>/<hash>_<original_name>.webp
```

**Hash**: First 8 characters of SHA-256 content hash
**AI Description**: Sanitized, snake_case, max 50 chars
**Original Name**: Sanitized, no extension

## Category Rules

- **Default**: `photos`
- **CLI Override**: `--category <name>` flag
- **Auto-detect**:
  - Videos (mp4, mov, avi) → `videos`
  - GIFs (gif) → `gifs`
  - All others → default to `photos` unless overridden

## Image Processing Pipeline

### Standard Images (JPEG, PNG, etc)

1. **Load** with Pillow
2. **Strip Location EXIF** (GPS data only, keep other metadata)
3. **Resize** if `--full` not set:
   - Calculate dimensions at 75% quality target
   - Maintain aspect ratio
4. **Convert** to WebP at specified quality (default: 75%)
5. **Calculate** SHA-256 hash of processed image
6. **Check** for existing file with same hash
7. **Upload** to R2 if new

### GIFs

1. **Load** animated GIF
2. **Convert** all frames to WebP (maintain animation)
3. **Optimize** at 75% quality
4. **Process** same as standard images

### Videos

1. **Validate** duration ≤ 10 seconds (error if longer)
2. **Extract** frames with ffmpeg:
   - Remove audio track
   - Scale to max 720p (maintain aspect ratio)
   - Sample at 10 fps
3. **Convert** to animated WebP at 75% quality
4. **Process** same as standard images

**ffmpeg command**:
```bash
ffmpeg -i input.mp4 -vf "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,fps=10" -c:v libwebp -quality 75 -an -loop 0 output.webp
```

## AI Analysis

### Providers

1. **Claude** (Anthropic API)
   - Model: `claude-sonnet-4-20250514`
   - For testing and high-quality analysis
   
2. **OpenRouter** (stub implementation)
   - Various cheaper models
   - To be implemented later

3. **Local Models** (future)
   - MLX / LM Studio integration
   - Model TBD based on research

### Batch Processing

- **If provider supports batch**: Send all images in one API call
- **If not**: Upload in parallel (asyncio/threads)
- **Fallback**: Sequential processing

### Metadata Generated

```json
{
  "description": "A golden sunset over calm ocean waters",  // max 15 words
  "alt_text": "Sunset over ocean with orange and pink sky reflecting on water",
  "tags": ["sunset", "ocean", "nature", "landscape", "evening"]
}
```

### AI Prompt Template

```
Analyze this image and provide:
1. A concise description (maximum 15 words)
2. Detailed alt text for accessibility (1-2 sentences)
3. 3-5 relevant tags for categorization

Return as JSON:
{
  "description": "...",
  "alt_text": "...",
  "tags": ["tag1", "tag2", ...]
}
```

### Caching

- **Cache analysis results** keyed by content hash
- **Store** in `~/.cache/cdn-cli/analysis.json`
- **Reuse** if same hash analyzed previously
- **TTL**: No expiration (content-addressed)

## CLI Interface

### Commands

```bash
cdn-upload [OPTIONS] [FILES...]
cdn-upload auth
cdn-upload list [OPTIONS]
```

### Global Options

```
--quality INTEGER        WebP quality 0-100 (default: 75)
--full                   Keep full resolution, no compression
--analyze                Enable AI analysis for descriptions/tags
--category TEXT          Override category (default: photos)
--output-format TEXT     Output format: plain|markdown|html (default: plain)
--dry-run               Preview without uploading
--help                  Show help message
```

### Upload Command

```bash
cdn-upload [FILES...] [OPTIONS]

FILES: One or more image files, video files, or document files (md, html)

Examples:
  cdn-upload photo.jpg
  cdn-upload *.png --analyze
  cdn-upload blog.md --output-format markdown
  cdn-upload video.mp4 --category videos
```

**Behavior**:
- **Images/Videos**: Process and upload, output CDN URLs
- **Documents** (md/html): Extract image references, upload non-CDN images, create new file with updated links

### Auth Command

```bash
cdn-upload auth

Validates secrets.json and tests R2 connection.
```

### List Command

```bash
cdn-upload list [--page INTEGER]

Shows recent uploads (10 per page):
- Filename
- Upload date/time
- File size
- Dimensions
- CDN URL
- AI description (if available)

Sorted by most recent first.
```

## Output Formats

### Plain (default)
```
https://cdn.autumnsgrove.com/photos/2025/03/16/sunset_a3f9b2c1.webp
https://cdn.autumnsgrove.com/photos/2025/03/16/beach_f7e2d9a4.webp
```

### Markdown
```markdown
![A golden sunset over calm ocean waters](https://cdn.autumnsgrove.com/photos/2025/03/16/sunset_a3f9b2c1.webp)
![Sandy beach with footprints at dusk](https://cdn.autumnsgrove.com/photos/2025/03/16/beach_f7e2d9a4.webp)
```

### HTML
```html
<img src="https://cdn.autumnsgrove.com/photos/2025/03/16/sunset_a3f9b2c1.webp" alt="A golden sunset over calm ocean waters">
<img src="https://cdn.autumnsgrove.com/photos/2025/03/16/beach_f7e2d9a4.webp" alt="Sandy beach with footprints at dusk">
```

### Clipboard

All URLs/formatted output automatically copied to clipboard after upload.

## Document Processing

### Supported Formats
- Markdown (.md)
- HTML (.html, .htm)

### Extraction Logic

**Markdown**:
```regex
!\[.*?\]\((.*?\.(?:jpg|jpeg|png|gif|webp))\)
<img.*?src=["'](.*?\.(?:jpg|jpeg|png|gif|webp))["']
```

**HTML**:
```regex
<img.*?src=["'](.*?\.(?:jpg|jpeg|png|gif|webp))["']
```

### Processing Flow

1. **Parse** document for image references
2. **Categorize** references:
   - Already on CDN (skip): `cdn.autumnsgrove.com`
   - Local file paths: Process and upload
   - External URLs: Skip (leave as-is)
3. **Upload** local images
4. **Replace** references in document
5. **Create** new file: `document_cdn.md` or `document_cdn.html`
6. **Report**:
   ```
   Processed: document.md
   Uploaded: 3 images
   Skipped: 2 images (already on CDN)
   Created: document_cdn.md
   ```

## Duplicate Detection

### Hash Calculation
```python
def calculate_hash(image_data: bytes) -> str:
    """Returns first 8 chars of SHA-256 hash"""
    return hashlib.sha256(image_data).hexdigest()[:8]
```

### Lookup Process

1. **Calculate** hash of processed image
2. **Query** R2 for existing files with pattern:
   ```
   {category}/{year}/{month}/{day}/*{hash}*.webp
   ```
3. **If found**: Return existing URL (skip upload)
4. **If not found**: Proceed with upload

### Edge Cases

- **Hash collision** (astronomically rare): Append random suffix `_1`, `_2`, etc.
- **Same image, different analysis**: Use cached analysis

## Error Handling

### Scenarios and Responses

| Error | Handling |
|-------|----------|
| Unsupported file format | Skip with warning, continue batch |
| Corrupted image | Skip with error message, continue batch |
| Network failure | Retry 3x with exponential backoff, then fail |
| R2 quota exceeded | Abort with clear error message |
| Invalid credentials | Fail immediately with auth instructions |
| AI API failure | Warn, continue upload without metadata |
| Video too long (>10s) | Error with suggestion to trim |
| ffmpeg not installed | Error with installation instructions |

### Error Display (Rich)

```
❌ Error: Could not process corrupted_image.jpg (corrupted file)
⚠️  Warning: Skipping external URL (already hosted)
✓ Uploaded: photo.jpg → https://cdn.autumnsgrove.com/...
```

## Progress Indicators

### Single Upload
```
Processing photo.jpg... ━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:01
```

### Batch Upload
```
Processing 10 images
  photo1.jpg ━━━━━━━━━━━━━━━━━━━━━━ 100% ✓
  photo2.jpg ━━━━━━━━━━━━━━━━━━━━━━ 100% ✓
  photo3.jpg ━━━━━━━━━━━━━━━━━━━━━━  45%
  ...
Overall Progress: 7/10 ━━━━━━━━━━━━━━━  70%
```

### With AI Analysis
```
Analyzing images... ━━━━━━━━━━━━━━━━━━━━━━ 100%
Uploading images... ━━━━━━━━━━━━━━━━━━━━━━ 100%
```

## Configuration Management

### secrets.json Structure

```json
{
  "r2": {
    "account_id": "your_account_id",
    "access_key_id": "your_access_key",
    "secret_access_key": "your_secret_key",
    "bucket_name": "your_bucket_name",
    "custom_domain": "cdn.autumnsgrove.com"
  },
  "ai": {
    "anthropic_api_key": "sk-ant-...",
    "openrouter_api_key": null
  }
}
```

### Loading Config

```python
# config.py
def load_secrets() -> dict:
    """Load and validate secrets.json"""
    path = Path("secrets.json")
    if not path.exists():
        raise ConfigError("secrets.json not found. Copy from secrets.json.template")
    
    with open(path) as f:
        secrets = json.load(f)
    
    # Validate required fields
    required = ["r2.account_id", "r2.access_key_id", ...]
    for field in required:
        if not get_nested(secrets, field):
            raise ConfigError(f"Missing required field: {field}")
    
    return secrets
```

## R2 Integration

### Connection Setup

```python
import boto3

session = boto3.session.Session()
client = session.client(
    service_name='s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    region_name='auto'
)
```

### Upload Function

```python
def upload_to_r2(
    client,
    bucket: str,
    key: str,
    data: bytes,
    metadata: dict
) -> str:
    """Upload to R2 and return CDN URL"""
    
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType='image/webp',
        Metadata=metadata,
        CacheControl='public, max-age=31536000'  # 1 year
    )
    
    return f"https://cdn.autumnsgrove.com/{key}"
```

### List Recent

```python
def list_recent(client, bucket: str, limit: int = 10, offset: int = 0):
    """List recent uploads from R2"""
    
    response = client.list_objects_v2(
        Bucket=bucket,
        MaxKeys=1000,  # Get many, filter locally
        Prefix='photos/'  # Or other category
    )
    
    # Sort by LastModified descending
    objects = sorted(
        response.get('Contents', []),
        key=lambda x: x['LastModified'],
        reverse=True
    )
    
    # Paginate
    page = objects[offset:offset + limit]
    
    return page
```

## Dependencies

### Python Packages (pyproject.toml)

```toml
[project]
name = "cdn-upload-cli"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
    "pillow>=10.0.0",
    "boto3>=1.34.0",
    "anthropic>=0.18.0",
    "openai>=1.12.0",  # For OpenRouter
    "ffmpeg-python>=0.2.0",
    "pyperclip>=1.8.2",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.1.0",
]

[project.scripts]
cdn-upload = "cdn_upload.cli:app"
```

### System Dependencies

- **ffmpeg**: Required for video processing
  - macOS: `brew install ffmpeg`
  - Linux: `apt-get install ffmpeg` or `yum install ffmpeg`
  - Windows: Download from ffmpeg.org

## Testing Checklist

- [ ] Single image upload (JPEG, PNG)
- [ ] Batch image upload
- [ ] GIF upload (animated)
- [ ] Video upload (< 10s)
- [ ] Video upload (> 10s, should error)
- [ ] Duplicate detection
- [ ] AI analysis (single image)
- [ ] AI analysis (batch)
- [ ] Markdown file processing
- [ ] HTML file processing
- [ ] Auth validation
- [ ] List command (pagination)
- [ ] All output formats (plain, markdown, html)
- [ ] Clipboard copy
- [ ] Dry run mode
- [ ] Error handling (corrupted image, network failure, etc)
- [ ] Progress indicators
- [ ] Custom quality setting
- [ ] Full resolution flag
- [ ] Custom category

## Future Enhancements

- [ ] Local model integration (MLX, LM Studio)
- [ ] Delete command (remove from R2)
- [ ] Metadata editing (update descriptions)
- [ ] Search uploaded images by tag/description
- [ ] Image transformation (crop, rotate) before upload
- [ ] Webhook notifications on upload
- [ ] Statistics (total storage used, bandwidth)
- [ ] Export catalog as JSON/CSV
- [ ] Thumbnail generation
- [ ] Image gallery generator