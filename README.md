# Press

> Raw in. Ready out. Going to press.

A fast, intelligent CLI for converting raw photos into web-ready images. Press handles the complete pipeline—JPEG XL conversion, AI-powered descriptions, duplicate detection, and upload to Cloudflare R2.

## Sample Output

![Sample upload with AI analysis](https://cdn.grove.place/autumn/2026/01/21/e2c7f6e5_photo_to_upload.jxl)

*Uploaded with AI-generated filename based on image content*

## Features

- **JPEG XL Default**: Superior compression with lossless JPEG transcoding (WebP fallback available)
- **AI Analysis** (optional): Auto-generate descriptions, alt text, and tags using Cloudflare Workers AI (default), Claude, or local MLX
- **Batch Processing**: Upload multiple images in parallel with progress tracking
- **Link Management**: Auto-copy CDN links to clipboard in plain, Markdown, or HTML format
- **Document Processing**: Extract images from Markdown/HTML files and replace with CDN links
- **Video Support**: Convert videos to optimized silent WebP animations (max 10s, 720p)
- **GIF Handling**: Preserve animations while converting to WebP
- **Duplicate Detection**: SHA-256 content hashing prevents re-uploads
- **User Organization**: Organize by username and date (`autumn/2026/01/21/...`)

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv)

### Install as UV Tool (Recommended)

```bash
# Clone and install globally
git clone <repo>
cd CDNUploader
uv tool install .

# Now accessible from anywhere
press --help
```

### Install for Development

```bash
git clone <repo>
cd CDNUploader
uv pip install -e ".[dev]"
```

## Configuration

### Quick Setup (Recommended)

If you have [Wrangler](https://developers.cloudflare.com/workers/wrangler/) installed and logged in:

```bash
press setup
```

This will detect your Cloudflare account, list your R2 buckets, and help create `secrets.json`.

### Manual Setup

1. Copy the template:
   ```bash
   cp secrets.json.template ~/.config/cdn-upload/secrets.json
   ```

2. Fill in your credentials (see below for where to find each one)

### Where to Find Your Credentials

| Field | Where to Find It |
|-------|------------------|
| **account_id** | [Cloudflare Dashboard](https://dash.cloudflare.com) → Any domain → **Overview** → right sidebar under "API" → **Account ID** |
| **access_key_id** | [R2 Overview](https://dash.cloudflare.com/?to=/:account/r2/api-tokens) → **Manage R2 API Tokens** → Create token → Copy **Access Key ID** |
| **secret_access_key** | Same as above → Copy **Secret Access Key** (shown only once!) |
| **bucket_name** | [R2 Overview](https://dash.cloudflare.com/?to=/:account/r2/overview) → Your bucket's name |
| **custom_domain** | [R2 Bucket](https://dash.cloudflare.com/?to=/:account/r2/overview) → Click bucket → **Settings** → **Public access** → Custom domain |
| **username** | Your username for CDN path prefix (e.g., `autumn`) |

**Tip**: If you have Wrangler installed, you can also find your account ID with:
```bash
wrangler whoami
```

### Optional: AI Analysis

For AI-powered image descriptions, add your Cloudflare Workers AI token (recommended) or Claude API key as fallback.

**Cloudflare Workers AI (default, near-zero cost):**
1. Go to [Workers AI API Tokens](https://dash.cloudflare.com/?to=/:account/ai/workers-ai)
2. Create a token with Workers AI permissions
3. Add to secrets.json:
```json
"ai": {
  "cloudflare_ai_token": "your_token_here"
}
```

**Claude API (fallback):**
```json
"ai": {
  "anthropic_api_key": "sk-ant-..."
}
```
Use with `--provider claude` flag.

## Quick Start

```bash
# Verify configuration
press auth

# Upload a single image
press upload image.jpg

# Upload with AI analysis
press upload image.jpg --analyze

# Batch upload
press upload *.jpg --analyze

# Process markdown file (uploads images, rewrites links)
press upload document.md

# List recent uploads
press list
```

## Usage Examples

```bash
# Basic upload (JPEG XL default)
press upload photo.jpg

# Choose output format
press upload photo.jpg --format jxl      # JPEG XL (default)
press upload photo.jpg --format webp     # WebP fallback
press upload photo.jpg --format both     # Upload both formats

# Upload with custom quality (0-100)
press upload photo.jpg --quality 85

# Full resolution with lossless JPEG→JXL transcoding
press upload photo.jpg --full

# AI analysis
press upload diagram.png --analyze

# Dry run to preview
press upload *.jpg --dry-run

# Output as Markdown image syntax
press upload photo.jpg --output-format markdown

# List uploads with pagination
press list --page 2
```

## How It Works

1. **Image Processing**: Converts to JPEG XL (or WebP), strips EXIF GPS data, optimizes quality
2. **Content Hashing**: SHA-256 hash of processed content for duplicate detection
3. **AI Analysis**: Optional Claude vision API generates description for smart filenames
4. **R2 Upload**: Uploads to Cloudflare R2 with 1-year cache headers
5. **URL Generation**: Returns CDN URL and copies to clipboard

## Development

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=cdn_upload

# Type checking
uv run mypy cdn_upload
```

### Tech Stack

- `typer` - CLI framework
- `rich` - Terminal formatting and progress bars
- `boto3` - S3/R2 uploads
- `pillow` - Image processing
- `pillow-jxl-plugin` - JPEG XL encoding
- `cloudflare Workers AI` - AI image analysis (default, via REST API)
- `anthropic` - Claude AI analysis (fallback)
- `beautifulsoup4` - HTML/Markdown parsing
- `ffmpeg` - Video processing (external dependency)

## License

MIT
