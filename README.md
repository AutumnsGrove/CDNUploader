## README.md

```markdown
# CDN Upload CLI

A fast, intelligent CLI tool for uploading and managing images on your Cloudflare R2 CDN with automatic optimization, AI analysis, and batch processing.

## Features

- 🚀 **Smart Upload**: Automatic WebP conversion with quality optimization
- 🧠 **AI Analysis** (optional): Auto-generate descriptions, alt text, and tags using Claude or local models
- 📦 **Batch Processing**: Upload multiple images in parallel with progress tracking
- 🔗 **Link Management**: Auto-copy CDN links to clipboard in plain, Markdown, or HTML format
- 📝 **Document Processing**: Extract images from Markdown/HTML files and replace with CDN links
- 🎬 **Video Support**: Convert videos to optimized silent WebP GIFs (max 10s, 720p)
- 🎨 **GIF Handling**: Preserve animations while converting to WebP
- 🔍 **Duplicate Detection**: Content-based hashing prevents re-uploads
- 📊 **List Recent**: Browse uploaded images with descriptions and metadata
- 🎯 **Category Organization**: Organize by type and date (`photos/2025/03/16/...`)

## Quick Start

```bash
# Install with uv
uv pip install -e .

# First time setup
cdn-upload auth

# Upload a single image
cdn-upload image.jpg

# Upload with AI analysis
cdn-upload image.jpg --analyze

# Batch upload
cdn-upload *.jpg --analyze

# Process markdown file
cdn-upload document.md --output-format markdown

# List recent uploads
cdn-upload list
```

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv)

```bash
git clone <repo>
cd cdn-upload-cli
cp secrets.json.template secrets.json
# Edit secrets.json with your credentials
uv pip install -e .
```

## Configuration

Edit `secrets.json` with your Cloudflare R2 credentials:
- Account ID
- Access Key ID
- Secret Access Key
- Bucket Name
- Custom Domain (cdn.autumnsgrove.com)

Optional AI provider keys:
- Anthropic API Key (for Claude)
- OpenRouter API Key (for alternative models)

## Usage Examples

```bash
# Basic upload
cdn-upload photo.jpg

# Upload with custom quality
cdn-upload photo.jpg --quality 85

# Full resolution (no compression)
cdn-upload photo.jpg --full

# AI analysis with custom category
cdn-upload diagram.png --analyze --category diagrams

# Dry run to preview
cdn-upload *.jpg --dry-run

# Markdown with AI analysis
cdn-upload blog-post.md --analyze --output-format markdown

# List recent uploads
cdn-upload list --page 2
```

## Development

Built with:
- `typer` - CLI framework
- `rich` - Terminal formatting
- `boto3` - S3/R2 uploads
- `pillow` - Image processing
- `anthropic` / `openai` - AI analysis
- `ffmpeg-python` - Video processing