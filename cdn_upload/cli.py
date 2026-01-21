"""CLI interface for CDN Upload using Typer.

Main entry point for the application. Handles command definitions,
argument parsing, progress bars, and Rich console output.
"""

from pathlib import Path
from typing import Optional
from datetime import datetime
import json
import subprocess
import shutil

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .config import load_secrets, validate_config, get_r2_config, get_ai_config, ConfigError, get_config_dir
from .models import ProcessingOptions, UploadResult
from .process import process_image, process_gif, process_video, detect_file_type
from .storage import calculate_hash, build_object_key, get_date_path, generate_filename
from .upload import init_r2_client, upload_file, batch_upload, batch_delete, verify_connection, list_recent_uploads, check_duplicate
from .ai import analyze_image, batch_analyze
from .parser import extract_images, categorize_reference, rewrite_document, save_new_document, detect_document_type, resolve_local_path
from .utils import copy_to_clipboard, format_output, format_file_size, print_success, print_error, print_warning

# Supported file extensions for folder expansion
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff',  # images
    '.gif',  # gifs
    '.mp4', '.mov', '.avi', '.webm',  # videos
    '.md', '.markdown', '.html', '.htm',  # documents
}

# History file location
HISTORY_FILE = Path.home() / ".cdn-upload-history.json"


def load_history() -> list[dict]:
    """Load upload history from file."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_history(history: list[dict]) -> None:
    """Save upload history to file."""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2, default=str)


def add_batch_to_history(uploads: list[dict]) -> None:
    """Add a batch of uploads to history.

    Args:
        uploads: List of dicts with 'key' and 'url' for each upload
    """
    if not uploads:
        return

    history = load_history()
    batch = {
        "timestamp": datetime.now().isoformat(),
        "count": len(uploads),
        "uploads": uploads
    }
    history.append(batch)

    # Keep only last 50 batches
    if len(history) > 50:
        history = history[-50:]

    save_history(history)


def expand_paths(paths: list[Path]) -> list[Path]:
    """Expand paths, recursively finding files in directories.

    Args:
        paths: List of file or directory paths

    Returns:
        List of file paths (directories expanded to their contents)
    """
    expanded = []

    for path in paths:
        if path.is_dir():
            # Recursively find all supported files in directory
            for ext in SUPPORTED_EXTENSIONS:
                expanded.extend(path.rglob(f"*{ext}"))
        else:
            expanded.append(path)

    # Sort by name for consistent ordering
    return sorted(expanded, key=lambda p: p.name.lower())


app = typer.Typer(
    name="cdn-upload",
    help="Upload images to Cloudflare R2 CDN with automatic optimization",
    add_completion=False,
)
console = Console()


@app.command()
def upload(
    files: list[Path] = typer.Argument(
        ...,
        help="Image files, video files, document files (md, html), or folders to upload",
        exists=True,
    ),
    quality: int = typer.Option(
        85,
        "--quality",
        "-q",
        help="WebP quality 0-100",
        min=0,
        max=100,
    ),
    full: bool = typer.Option(
        False,
        "--full",
        "-f",
        help="Keep full resolution (still converts to WebP)",
    ),
    skip_compression: bool = typer.Option(
        False,
        "--skip-compression",
        "-s",
        help="Upload original file without WebP conversion",
    ),
    analyze: bool = typer.Option(
        False,
        "--analyze",
        "-a",
        help="Enable AI analysis for descriptions/tags",
    ),
    category: str = typer.Option(
        "photos",
        "--category",
        "-c",
        help="Override category (default: photos)",
    ),
    output_format: str = typer.Option(
        "plain",
        "--output-format",
        "-o",
        help="Output format: plain|markdown|html",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Preview without uploading",
    ),
    provider: str = typer.Option(
        "claude",
        "--provider",
        "-p",
        help="AI provider: claude|mlx",
    ),
) -> None:
    """Upload files to CDN.

    Supports images, videos, and documents (Markdown/HTML).
    """
    try:
        # Load configuration
        secrets = load_secrets()
        validate_config(secrets)
        r2_config = get_r2_config(secrets)
        ai_config = get_ai_config(secrets)

        # Expand directories to individual files
        expanded_files = expand_paths(files)

        if not expanded_files:
            console.print("[yellow]No supported files found[/yellow]")
            raise typer.Exit(0)

        # Show count if folders were expanded
        if len(expanded_files) != len(files):
            console.print(f"[dim]Found {len(expanded_files)} files to process[/dim]\n")

        # Initialize R2 client
        if not dry_run:
            client = init_r2_client(r2_config)

        results = []
        all_urls = []
        batch_uploads = []  # Track new uploads for history

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task("[cyan]Processing files...", total=len(expanded_files))

            for file_path in expanded_files:
                file_type = detect_file_type(file_path)
                progress.update(task, description=f"[cyan]Processing {file_path.name}...")
                progress.refresh()  # Force display update

                if file_type == 'document':
                    # Handle document files
                    urls = process_document(
                        file_path, client if not dry_run else None, r2_config, ai_config,
                        quality, full, analyze, category, output_format, dry_run, progress, provider,
                        skip_compression
                    )
                    all_urls.extend(urls)

                elif file_type in ('image', 'gif', 'video'):
                    # Handle media files
                    result = process_media_file(
                        file_path, client if not dry_run else None, r2_config, ai_config,
                        quality, full, analyze, category, file_type, dry_run, provider,
                        skip_compression
                    )
                    if result:
                        all_urls.append(result["url"])
                        results.append((file_path.name, result["url"]))
                        # Track new uploads for history
                        if result.get("new") and result.get("key"):
                            batch_uploads.append({"key": result["key"], "url": result["url"]})

                else:
                    print_warning(f"Unsupported file type: {file_path}")

                progress.advance(task)

        # Save batch to history (only if there were actual uploads)
        if batch_uploads and not dry_run:
            add_batch_to_history(batch_uploads)

        # Output results
        if all_urls:
            # Format output based on type
            if output_format == 'plain':
                output = '\n'.join(all_urls)
            elif output_format == 'markdown':
                output = '\n'.join(f"![]({url})" for url in all_urls)
            elif output_format == 'html':
                output = '\n'.join(f'<img src="{url}">' for url in all_urls)
            else:
                output = '\n'.join(all_urls)

            console.print("\n[bold green]Upload complete![/bold green]\n")
            console.print(output)

            # Copy to clipboard
            if len(all_urls) == 1:
                copy_to_clipboard(all_urls[0])
                console.print("\n[dim]URL copied to clipboard[/dim]")
            else:
                copy_to_clipboard(output)
                console.print(f"\n[dim]{len(all_urls)} URLs copied to clipboard[/dim]")
        else:
            console.print("[yellow]No files were uploaded[/yellow]")

    except ConfigError as e:
        print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Upload failed: {e}")
        raise typer.Exit(1)


def process_media_file(
    file_path: Path,
    client,
    r2_config,
    ai_config,
    quality: int,
    full: bool,
    analyze: bool,
    category: str,
    file_type: str,
    dry_run: bool,
    provider: str = "claude",
    skip_compression: bool = False,
) -> dict | None:
    """Process and upload a single media file.

    Returns:
        Dict with 'key' and 'url', or None if failed
    """
    try:
        # Read original file
        with open(file_path, 'rb') as f:
            original_data = f.read()

        # Determine if we should skip compression
        if skip_compression and file_type == 'image':
            # Upload original file without conversion
            upload_data = original_data
            file_extension = file_path.suffix.lower()
        else:
            # Process based on type (convert to WebP)
            if file_type == 'image':
                upload_data, dimensions = process_image(file_path, quality, full)
            elif file_type == 'gif':
                upload_data, dimensions = process_gif(file_path, quality)
            elif file_type == 'video':
                upload_data, dimensions = process_video(file_path, quality)
            else:
                return None
            file_extension = '.webp'

        # Calculate hash
        content_hash = calculate_hash(upload_data)

        # Get AI analysis if requested
        metadata = None
        if analyze:
            # Check if we have required credentials for the provider
            if provider == "claude" and not ai_config.anthropic_api_key:
                print_warning("Anthropic API key not configured, skipping analysis")
            elif provider == "mlx":
                # MLX runs locally, no API key needed
                metadata = analyze_image(upload_data, ai_config, content_hash, provider)
            else:
                metadata = analyze_image(upload_data, ai_config, content_hash, provider)

        # Build object key using username from config
        date_path = get_date_path()
        filename = generate_filename(
            file_path.stem,
            content_hash,
            metadata.description if metadata else None,
            file_extension
        )
        object_key = build_object_key(r2_config.username, date_path, filename)

        if dry_run:
            console.print(f"[dim]Would upload: {file_path.name} → {object_key}[/dim]")
            url = f"https://{r2_config.custom_domain}/{object_key}"
            return {"key": object_key, "url": url, "new": False}  # dry run, don't track

        # Check for duplicate
        existing_url = check_duplicate(
            client, r2_config.bucket_name, r2_config.custom_domain,
            r2_config.username, date_path, content_hash
        )
        if existing_url:
            console.print(f"[yellow]Duplicate found:[/yellow] {file_path.name}")
            return {"key": None, "url": existing_url, "new": False}  # duplicate, don't track

        # Upload
        url = upload_file(
            client,
            r2_config.bucket_name,
            object_key,
            upload_data,
            r2_config.custom_domain
        )

        return {"key": object_key, "url": url, "new": True}  # new upload, track it

    except Exception as e:
        print_error(f"Failed to process {file_path.name}: {e}")
        return None


def process_document(
    file_path: Path,
    client,
    r2_config,
    ai_config,
    quality: int,
    full: bool,
    analyze: bool,
    category: str,
    output_format: str,
    dry_run: bool,
    progress,
    provider: str = "claude",
    skip_compression: bool = False,
) -> list[str]:
    """Process a document file and upload its images."""
    urls = []

    try:
        # Read document
        content = file_path.read_text()
        doc_type = detect_document_type(file_path)

        # Extract images
        image_refs = extract_images(content, doc_type)

        if not image_refs:
            console.print(f"[yellow]No images found in {file_path.name}[/yellow]")
            return urls

        # Filter to local images only
        local_refs = [
            ref for ref in image_refs
            if categorize_reference(ref, r2_config.custom_domain) == 'local'
        ]

        if not local_refs:
            console.print(f"[yellow]No local images to upload in {file_path.name}[/yellow]")
            return urls

        # Process and upload each image
        replacements = {}
        for ref in local_refs:
            img_path = resolve_local_path(ref, file_path)

            if not img_path.exists():
                print_warning(f"Image not found: {ref}")
                continue

            url = process_media_file(
                img_path, client, r2_config, ai_config,
                quality, full, analyze, category,
                detect_file_type(img_path), dry_run, provider,
                skip_compression
            )

            if url:
                replacements[ref] = url
                urls.append(url)

        # Rewrite document with CDN URLs
        if replacements and not dry_run:
            new_content = rewrite_document(content, replacements, doc_type)
            new_path = save_new_document(file_path, new_content)
            console.print(f"[green]Created:[/green] {new_path.name}")

    except Exception as e:
        print_error(f"Failed to process document {file_path.name}: {e}")

    return urls


@app.command()
def auth() -> None:
    """Validate secrets.json and test R2 connection."""
    try:
        with console.status("[bold green]Validating configuration..."):
            secrets = load_secrets()
            validate_config(secrets)

        console.print("[green]✓[/green] Configuration valid")

        # Test R2 connection
        r2_config = get_r2_config(secrets)
        client = init_r2_client(r2_config)

        with console.status("[bold green]Testing R2 connection..."):
            verify_connection(client, r2_config.bucket_name)

        console.print("[green]✓[/green] R2 connection successful")
        console.print(f"  Bucket: {r2_config.bucket_name}")
        console.print(f"  Domain: {r2_config.custom_domain}")

        # Check AI config
        ai_config = get_ai_config(secrets)
        if ai_config.anthropic_api_key:
            console.print("[green]✓[/green] Anthropic API key configured")
        else:
            console.print("[yellow]![/yellow] Anthropic API key not configured (AI analysis disabled)")

    except ConfigError as e:
        console.print(f"[red]✗[/red] Configuration error: {e}")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]✗[/red] Connection error: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number (10 items per page)",
        min=1,
    ),
    category: str = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category",
    ),
) -> None:
    """List recent uploads with metadata.

    Shows filename, upload date, size, and CDN URL.
    """
    try:
        secrets = load_secrets()
        validate_config(secrets)
        r2_config = get_r2_config(secrets)

        client = init_r2_client(r2_config)

        # Calculate offset
        limit = 10
        offset = (page - 1) * limit

        with console.status("[bold green]Fetching uploads..."):
            uploads = list_recent_uploads(
                client,
                r2_config.bucket_name,
                r2_config.custom_domain,
                limit=limit,
                offset=offset,
                category=category
            )

        if not uploads:
            console.print("[yellow]No uploads found[/yellow]")
            return

        # Create table
        table = Table(title=f"Recent Uploads (Page {page})")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Modified", style="dim")
        table.add_column("URL", style="green")

        for upload in uploads:
            filename = Path(upload['key']).name
            size = format_file_size(upload['size'])
            modified = upload['modified'].strftime("%Y-%m-%d %H:%M")
            url = upload['url']

            table.add_row(filename, size, modified, url)

        console.print(table)

        if len(uploads) == limit:
            console.print(f"\n[dim]Use --page {page + 1} to see more[/dim]")

    except ConfigError as e:
        print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Failed to list uploads: {e}")
        raise typer.Exit(1)


@app.command()
def undo(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete the most recent batch of uploads from CDN.

    Removes all files from the last upload operation.
    """
    try:
        # Load history
        history = load_history()

        if not history:
            console.print("[yellow]No upload history found[/yellow]")
            raise typer.Exit(0)

        # Get the latest batch
        latest = history[-1]
        uploads = latest.get("uploads", [])
        timestamp = latest.get("timestamp", "Unknown")

        if not uploads:
            console.print("[yellow]Latest batch has no uploads to delete[/yellow]")
            raise typer.Exit(0)

        # Parse and format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            formatted_time = timestamp

        # Show what will be deleted
        console.print(f"\n[bold]Latest batch ({formatted_time}):[/bold]")
        console.print(f"  Files: {len(uploads)}")
        console.print("\n[dim]Files to delete:[/dim]")
        for upload in uploads:
            filename = Path(upload['key']).name
            console.print(f"  • {filename}")

        # Confirm deletion
        if not force:
            console.print("")
            confirm = typer.confirm("Delete these files from CDN?", default=False)
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(0)

        # Load config and initialize client
        secrets = load_secrets()
        validate_config(secrets)
        r2_config = get_r2_config(secrets)
        client = init_r2_client(r2_config)

        # Delete files
        keys = [upload['key'] for upload in uploads]

        with console.status("[bold red]Deleting files..."):
            deleted, failed = batch_delete(client, r2_config.bucket_name, keys)

        # Remove batch from history
        history.pop()
        save_history(history)

        # Report results
        if failed == 0:
            console.print(f"\n[green]✓ Deleted {deleted} files[/green]")
        else:
            console.print(f"\n[yellow]Deleted {deleted} files, {failed} failed[/yellow]")

    except ConfigError as e:
        print_error(f"Configuration error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Undo failed: {e}")
        raise typer.Exit(1)


@app.command()
def history(
    count: int = typer.Option(
        5,
        "--count",
        "-n",
        help="Number of recent batches to show",
    ),
) -> None:
    """Show recent upload batches.

    Displays timestamp and file count for recent uploads.
    """
    batches = load_history()

    if not batches:
        console.print("[yellow]No upload history found[/yellow]")
        return

    # Show recent batches (most recent first)
    recent = list(reversed(batches[-count:]))

    table = Table(title="Recent Upload Batches")
    table.add_column("#", style="dim")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Files", justify="right")

    for i, batch in enumerate(recent):
        timestamp = batch.get("timestamp", "Unknown")
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            formatted = timestamp

        file_count = str(batch.get("count", len(batch.get("uploads", []))))
        table.add_row(str(i + 1), formatted, file_count)

    console.print(table)
    console.print(f"\n[dim]Use 'cdn-upload undo' to delete the most recent batch[/dim]")


@app.command()
def setup() -> None:
    """Interactive setup wizard for secrets.json.

    Detects Wrangler config to pre-fill account ID and bucket names.
    """
    console.print("\n[bold]CDN Upload Setup Wizard[/bold]\n")

    secrets_path = get_config_dir() / "secrets.json"
    template = {
        "r2": {
            "account_id": "",
            "access_key_id": "",
            "secret_access_key": "",
            "bucket_name": "",
            "custom_domain": ""
        },
        "ai": {
            "anthropic_api_key": "",
            "openrouter_api_key": None
        }
    }

    # Check if secrets already exist
    if secrets_path.exists():
        console.print(f"[yellow]Found existing config at:[/yellow] {secrets_path}")
        if not typer.confirm("Overwrite with new setup?", default=False):
            console.print("[dim]Setup cancelled[/dim]")
            raise typer.Exit(0)

    # Check for Wrangler
    wrangler_path = shutil.which("wrangler")
    account_id = None
    buckets = []

    if wrangler_path:
        console.print("[green]✓[/green] Wrangler detected\n")

        # Try to get account info
        with console.status("[dim]Fetching account info...[/dim]"):
            try:
                result = subprocess.run(
                    ["wrangler", "whoami"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode == 0:
                    # Parse account ID from output
                    for line in result.stdout.split('\n'):
                        if 'Account ID' in line or 'account_id' in line.lower():
                            # Extract ID (usually in format "Account ID: abc123" or similar)
                            parts = line.split(':')
                            if len(parts) >= 2:
                                account_id = parts[-1].strip()
                        # Also check for format like "│ abc123 │ Account Name │"
                        if '│' in line and len(line.split('│')) >= 3:
                            parts = [p.strip() for p in line.split('│') if p.strip()]
                            if len(parts) >= 1 and len(parts[0]) == 32:
                                account_id = parts[0]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if account_id:
            console.print(f"[green]✓[/green] Found Account ID: [cyan]{account_id}[/cyan]")
            template["r2"]["account_id"] = account_id

        # Try to list R2 buckets
        with console.status("[dim]Listing R2 buckets...[/dim]"):
            try:
                result = subprocess.run(
                    ["wrangler", "r2", "bucket", "list"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if result.returncode == 0:
                    # Parse bucket names from output
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        # Skip empty lines and headers
                        if not line or line.startswith('name') or line.startswith('-'):
                            continue
                        # Bucket names are usually the first column
                        if '│' in line:
                            parts = [p.strip() for p in line.split('│') if p.strip()]
                            if parts:
                                buckets.append(parts[0])
                        elif line and not line.startswith('[') and not line.startswith('Using'):
                            # Simple format: just bucket name per line
                            buckets.append(line.split()[0] if line.split() else line)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if buckets:
            console.print(f"[green]✓[/green] Found {len(buckets)} R2 bucket(s):\n")
            for i, bucket in enumerate(buckets, 1):
                console.print(f"  {i}. {bucket}")

            console.print("")
            if len(buckets) == 1:
                template["r2"]["bucket_name"] = buckets[0]
                console.print(f"[dim]Auto-selected:[/dim] {buckets[0]}")
            else:
                choice = typer.prompt(
                    "Select bucket number (or enter name manually)",
                    default="1"
                )
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(buckets):
                        template["r2"]["bucket_name"] = buckets[idx]
                    else:
                        template["r2"]["bucket_name"] = choice
                except ValueError:
                    template["r2"]["bucket_name"] = choice
    else:
        console.print("[yellow]![/yellow] Wrangler not found - manual setup required\n")
        console.print("[dim]Install Wrangler for easier setup: npm install -g wrangler[/dim]\n")

    # Show what's still needed
    console.print("\n[bold]Credentials still needed:[/bold]\n")

    missing = []
    if not template["r2"]["account_id"]:
        missing.append(("account_id", "Dashboard → Overview → API section"))
    if not template["r2"]["access_key_id"]:
        missing.append(("access_key_id", "R2 → Manage API Tokens → Create"))
    if not template["r2"]["secret_access_key"]:
        missing.append(("secret_access_key", "Same as above (shown only once!)"))
    if not template["r2"]["bucket_name"]:
        missing.append(("bucket_name", "R2 → Your bucket name"))
    missing.append(("custom_domain", "R2 → Bucket → Settings → Custom domain"))

    for field, hint in missing:
        console.print(f"  • [cyan]{field}[/cyan]: {hint}")

    console.print("\n[dim]Quick links:[/dim]")
    console.print("  • R2 API Tokens: https://dash.cloudflare.com/?to=/:account/r2/api-tokens")
    console.print("  • R2 Buckets: https://dash.cloudflare.com/?to=/:account/r2/overview")

    # Save template
    console.print(f"\n[bold]Saving config to:[/bold] {secrets_path}\n")

    get_config_dir()  # Ensure directory exists
    with open(secrets_path, 'w') as f:
        json.dump(template, f, indent=2)

    console.print("[green]✓[/green] Config file created!")
    console.print(f"\n[dim]Edit the file to add your credentials:[/dim]")
    console.print(f"  nano {secrets_path}")
    console.print(f"\n[dim]Then verify with:[/dim]")
    console.print("  cdn-upload auth")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
