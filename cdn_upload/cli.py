"""CLI interface for CDN Upload using Typer.

Main entry point for the application. Handles command definitions,
argument parsing, progress bars, and Rich console output.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .config import load_secrets, validate_config, get_r2_config, get_ai_config, ConfigError
from .models import ProcessingOptions, UploadResult
from .process import process_image, process_gif, process_video, detect_file_type
from .storage import calculate_hash, build_object_key, determine_category, get_date_path, generate_filename
from .upload import init_r2_client, upload_file, batch_upload, verify_connection, list_recent_uploads, check_duplicate
from .ai import analyze_image, batch_analyze
from .parser import extract_images, categorize_reference, rewrite_document, save_new_document, detect_document_type, resolve_local_path
from .utils import copy_to_clipboard, format_output, format_file_size, print_success, print_error, print_warning

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
        help="Image files, video files, or document files (md, html) to upload",
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
        help="Keep full resolution, no compression",
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

        # Initialize R2 client
        if not dry_run:
            client = init_r2_client(r2_config)

        results = []
        all_urls = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            task = progress.add_task("[cyan]Processing files...", total=len(files))

            for file_path in files:
                file_type = detect_file_type(file_path)
                progress.update(task, description=f"[cyan]Processing {file_path.name}...")

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
                    url = process_media_file(
                        file_path, client if not dry_run else None, r2_config, ai_config,
                        quality, full, analyze, category, file_type, dry_run, provider,
                        skip_compression
                    )
                    if url:
                        all_urls.append(url)
                        results.append((file_path.name, url))

                else:
                    print_warning(f"Unsupported file type: {file_path}")

                progress.advance(task)

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
) -> str | None:
    """Process and upload a single media file."""
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

        # Build object key
        detected_category = determine_category(file_path, category)
        date_path = get_date_path()
        filename = generate_filename(
            file_path.stem,
            content_hash,
            metadata.description if metadata else None,
            file_extension
        )
        object_key = build_object_key(detected_category, date_path, filename)

        if dry_run:
            console.print(f"[dim]Would upload: {file_path.name} → {object_key}[/dim]")
            return f"https://{r2_config.custom_domain}/{object_key}"

        # Check for duplicate
        existing_url = check_duplicate(
            client, r2_config.bucket_name, r2_config.custom_domain,
            detected_category, date_path, content_hash
        )
        if existing_url:
            console.print(f"[yellow]Duplicate found:[/yellow] {file_path.name}")
            return existing_url

        # Upload
        url = upload_file(
            client,
            r2_config.bucket_name,
            object_key,
            upload_data,
            r2_config.custom_domain
        )

        return url

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


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
