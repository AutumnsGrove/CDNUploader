"""CLI interface for CDN Upload using Typer.

Main entry point for the application. Handles command definitions,
argument parsing, progress bars, and Rich console output.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import load_secrets, validate_config, ConfigError
from .models import ProcessingOptions

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
        75,
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
) -> None:
    """Upload files to CDN.

    Supports images, videos, and documents (Markdown/HTML).
    """
    raise NotImplementedError("Upload command not yet implemented")


@app.command()
def auth() -> None:
    """Validate secrets.json and test R2 connection."""
    try:
        with console.status("[bold green]Validating configuration..."):
            secrets = load_secrets()
            validate_config(secrets)

        console.print("[green]✓[/green] Configuration valid")

        # TODO: Test R2 connection
        console.print("[yellow]![/yellow] R2 connection test not yet implemented")

    except ConfigError as e:
        console.print(f"[red]✗[/red] Configuration error: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_uploads(
    page: int = typer.Option(
        1,
        "--page",
        "-p",
        help="Page number (10 items per page)",
        min=1,
    ),
) -> None:
    """List recent uploads with metadata.

    Shows filename, upload date, size, dimensions, CDN URL, and AI description.
    """
    raise NotImplementedError("List command not yet implemented")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
