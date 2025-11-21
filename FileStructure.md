# Project File Structure

```
cdn-upload-cli/
│
├── cdn_upload/                 # Main package
│   ├── __init__.py            # Package initialization
│   ├── cli.py                 # CLI interface (Typer commands)
│   ├── upload.py              # R2 upload logic and batch handling
│   ├── process.py             # Image/video processing (Pillow, ffmpeg)
│   ├── ai.py                  # AI analysis integrations
│   ├── parser.py              # Markdown/HTML parsing
│   ├── storage.py             # Hash calculation, duplicate detection
│   ├── config.py              # Configuration and secrets management
│   ├── utils.py               # Utilities (clipboard, sanitize, etc)
│   └── models.py              # Data classes (ImageMetadata, UploadResult)
│
├── tests/                     # Test suite (future)
│   ├── test_upload.py
│   ├── test_process.py
│   └── test_parser.py
│
├── secrets.json.template       # Template for credentials
├── secrets.json               # Actual credentials (gitignored)
├── pyproject.toml             # Project config and dependencies
├── README.md                  # User documentation
├── ProjectSpec.md             # Implementation specification
└── .gitignore                 # Git ignore rules


## Module Responsibilities

### cli.py
- Typer application setup
- Command definitions (upload, auth, list)
- Argument parsing and validation
- Rich console output formatting
- Progress bar management
- Error display

**Key Functions**:
- `app()` - Main Typer app
- `upload_command()` - Handle file uploads
- `auth_command()` - Validate credentials
- `list_command()` - Display recent uploads

---

### upload.py
- R2 client initialization
- Single file upload
- Batch upload coordination
- Duplicate detection via hash lookup
- CDN URL generation
- Metadata storage

**Key Functions**:
- `init_r2_client()` - Create boto3 S3 client
- `upload_file()` - Upload single file to R2
- `batch_upload()` - Parallel upload multiple files
- `check_duplicate()` - Query R2 for existing hash
- `list_recent_uploads()` - Fetch recent files

---

### process.py
- Image loading and validation
- WebP conversion
- Quality optimization
- EXIF stripping (location data)
- Dimension scaling
- GIF animation preservation
- Video to WebP conversion
- ffmpeg integration

**Key Functions**:
- `process_image()` - Convert image to WebP
- `process_gif()` - Convert animated GIF
- `process_video()` - Convert video to WebP
- `strip_location_exif()` - Remove GPS data
- `calculate_dimensions()` - Scale to target quality

---

### ai.py
- AI provider abstraction
- Claude API integration
- OpenRouter stub
- Local model stub (future)
- Batch analysis
- Response parsing
- Cache management

**Key Functions**:
- `analyze_image()` - Get metadata from AI
- `batch_analyze()` - Process multiple images
- `_call_claude()` - Claude API request
- `_call_openrouter()` - OpenRouter stub
- `_call_local()` - Local model stub
- `load_cache()` / `save_cache()` - Analysis caching

---

### parser.py
- Markdown parsing
- HTML parsing
- Image reference extraction
- Link categorization (local/external/cdn)
- Document rewriting
- New file generation

**Key Functions**:
- `extract_images()` - Find all image references
- `categorize_reference()` - Determine reference type
- `rewrite_document()` - Replace links with CDN URLs
- `save_new_document()` - Create `_cdn` version

---

### storage.py
- Content hash calculation
- File naming logic
- Category determination
- Date path generation
- Filename sanitization

**Key Functions**:
- `calculate_hash()` - SHA-256 hash
- `generate_filename()` - Create final filename
- `determine_category()` - Auto-detect or use flag
- `sanitize_name()` - Clean strings for URLs
- `get_date_path()` - Generate `YYYY/MM/DD` path

---

### config.py
- secrets.json loading
- Configuration validation
- R2 credentials management
- AI API keys
- Cache directory setup

**Key Functions**:
- `load_secrets()` - Read and validate secrets.json
- `validate_config()` - Check required fields
- `get_cache_dir()` - Ensure cache directory exists
- `get_r2_config()` - Extract R2 credentials
- `get_ai_config()` - Extract AI credentials

---

### utils.py
- Clipboard operations
- File format detection
- Progress bar helpers
- Rich formatting utilities
- Error formatting

**Key Functions**:
- `copy_to_clipboard()` - Cross-platform clipboard
- `format_markdown()` - Generate markdown output
- `format_html()` - Generate HTML output
- `detect_file_type()` - Determine image/video/document
- `format_file_size()` - Human-readable sizes

---

### models.py
- Data class definitions
- Type hints
- Serialization/deserialization

**Key Classes**:
```python
@dataclass
class ImageMetadata:
    description: str
    alt_text: str
    tags: list[str]

@dataclass
class UploadResult:
    url: str
    filename: str
    hash: str
    size: int
    dimensions: tuple[int, int]
    metadata: ImageMetadata | None
    
@dataclass
class ProcessingOptions:
    quality: int
    full_resolution: bool
    analyze: bool
    category: str
    output_format: str
```

---

## Data Flow

### Single Image Upload

```
User Input → cli.py
              ↓
      validate arguments
              ↓
      process.py (convert to WebP)
              ↓
      storage.py (calculate hash)
              ↓
      upload.py (check duplicate)
              ↓
      [if --analyze] → ai.py
              ↓
      upload.py (upload to R2)
              ↓
      utils.py (format output)
              ↓
      utils.py (copy to clipboard)
              ↓
      Display result to user
```

### Batch Upload

```
User Input → cli.py
              ↓
      validate arguments
              ↓
      [parallel processing]
        ├─ process.py (image 1)
        ├─ process.py (image 2)
        └─ process.py (image 3)
              ↓
      [if --analyze] → ai.py (batch)
              ↓
      [parallel uploads]
        ├─ upload.py (image 1)
        ├─ upload.py (image 2)
        └─ upload.py (image 3)
              ↓
      utils.py (format output)
              ↓
      utils.py (copy to clipboard)
              ↓
      Display results to user
```

### Document Processing

```
User Input → cli.py
              ↓
      parser.py (extract images)
              ↓
      categorize references
              ↓
      [for each local image]
        ↓
      process.py → upload.py
              ↓
      parser.py (rewrite document)
              ↓
      save new file (*_cdn.md)
              ↓
      Display summary to user