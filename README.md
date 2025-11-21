# CDN Upload CLI

A fast, intelligent CLI tool for uploading and managing images on your Cloudflare R2 CDN with automatic optimization, AI analysis, and batch processing.

## Sample Output

![Sample upload with AI analysis](https://cdn.autumnsgrove.com/photos/2025/11/20/person_with_curly_hair_holding_small_white_fluffy_6a9973a6.webp)

*Uploaded with AI-generated filename based on image content*

## Features

- **Smart Upload**: Automatic WebP conversion with quality optimization
- **AI Analysis** (optional): Auto-generate descriptions, alt text, and tags using Claude
- **Batch Processing**: Upload multiple images in parallel with progress tracking
- **Link Management**: Auto-copy CDN links to clipboard in plain, Markdown, or HTML format
- **Document Processing**: Extract images from Markdown/HTML files and replace with CDN links
- **Video Support**: Convert videos to optimized silent WebP animations (max 10s, 720p)
- **GIF Handling**: Preserve animations while converting to WebP
- **Duplicate Detection**: Content-based hashing prevents re-uploads
- **List Recent**: Browse uploaded images with descriptions and metadata
- **Category Organization**: Organize by type and date (`photos/2025/11/20/...`)

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv)

### Install as UV Tool (Recommended)

```bash
# Clone and install globally
git clone <repo>
cd CDNUploader
uv tool install .

# Now accessible from anywhere
cdn-upload --help
```

### Install for Development

```bash
git clone <repo>
cd CDNUploader
uv pip install -e ".[dev]"
```

## Configuration

Copy the template and add your credentials:

```bash
cp secrets.json.template secrets.json
```

Edit `secrets.json` with your Cloudflare R2 credentials:
- Account ID
- Access Key ID
- Secret Access Key
- Bucket Name
- Custom Domain

Optional AI provider key:
- Anthropic API Key (for Claude vision analysis)

## Quick Start

```bash
# Verify configuration
cdn-upload auth

# Upload a single image
cdn-upload upload image.jpg

# Upload with AI analysis
cdn-upload upload image.jpg --analyze

# Batch upload
cdn-upload upload *.jpg --analyze

# Process markdown file (uploads images, rewrites links)
cdn-upload upload document.md

# List recent uploads
cdn-upload list
```

## Usage Examples

```bash
# Basic upload
cdn-upload upload photo.jpg

# Upload with custom quality (0-100)
cdn-upload upload photo.jpg --quality 85

# Full resolution (no compression)
cdn-upload upload photo.jpg --full

# AI analysis with custom category
cdn-upload upload diagram.png --analyze --category diagrams

# Dry run to preview
cdn-upload upload *.jpg --dry-run

# Output as Markdown image syntax
cdn-upload upload photo.jpg --output-format markdown

# List uploads with pagination
cdn-upload list --page 2

# Filter by category
cdn-upload list --category screenshots
```

## How It Works

1. **Image Processing**: Converts to WebP, strips EXIF GPS data, resizes based on quality
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
- `anthropic` - Claude AI analysis
- `beautifulsoup4` - HTML/Markdown parsing
- `ffmpeg` - Video processing (external dependency)

## License

MIT
