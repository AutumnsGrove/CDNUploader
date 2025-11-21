# CDN Upload CLI - Implementation TODOs

## Phase 1: Core Infrastructure
- [ ] Implement `config.py` - secrets loading, validation
- [ ] Implement `models.py` - data classes (done - stubs created)
- [ ] Implement `utils.py` - clipboard, formatting helpers
- [ ] Implement `storage.py` - hash calculation, file naming

## Phase 2: Image Processing
- [ ] Implement `process.py` - WebP conversion with Pillow
- [ ] Add EXIF stripping (GPS data removal)
- [ ] Add dimension calculation and resizing
- [ ] Implement GIF to animated WebP conversion
- [ ] Implement video to WebP conversion (ffmpeg)
- [ ] Handle video duration validation (max 10s)

## Phase 3: Upload System
- [ ] Implement `upload.py` - R2 client initialization
- [ ] Add single file upload function
- [ ] Add batch upload with parallel processing
- [ ] Implement duplicate detection via hash lookup
- [ ] Add CDN URL generation
- [ ] Implement `list_recent_uploads` function

## Phase 4: CLI Interface
- [ ] Complete `cli.py` upload command
- [ ] Implement auth command (R2 connection test)
- [ ] Implement list command with pagination
- [ ] Add Rich progress bars and status indicators
- [ ] Add error display with colors
- [ ] Add clipboard copy on success

## Phase 5: AI Integration
- [ ] Implement `ai.py` Claude API integration
- [ ] Add AI analysis prompt and response parsing
- [ ] Implement analysis caching (by content hash)
- [ ] Add batch analysis support
- [ ] Create OpenRouter stub (future)
- [ ] Create local model stub (future)

## Phase 6: Document Parsing
- [ ] Implement `parser.py` - Markdown image extraction
- [ ] Add HTML image extraction
- [ ] Implement link categorization (local/external/cdn)
- [ ] Add document rewriting with CDN URLs
- [ ] Create `_cdn` suffix file generation

## Phase 7: Testing & Polish
- [ ] Write unit tests for all modules
- [ ] Add integration tests for full upload flow
- [ ] Test error handling scenarios
- [ ] Test all output formats (plain, markdown, html)
- [ ] Test dry-run mode
- [ ] Add comprehensive error messages
- [ ] Test on various image/video formats

## Future Enhancements
- [ ] Local model integration (MLX, LM Studio)
- [ ] Delete command (remove from R2)
- [ ] Metadata editing (update descriptions)
- [ ] Search uploaded images by tag/description
- [ ] Image transformation (crop, rotate)
- [ ] Webhook notifications
- [ ] Storage statistics
- [ ] Export catalog as JSON/CSV
