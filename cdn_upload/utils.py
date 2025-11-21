"""Utility functions for CDN Upload CLI.

Provides clipboard operations, output formatting, file type detection,
and other helper functions.
"""

from pathlib import Path

import pyperclip
from rich.console import Console

from .models import UploadResult


console = Console()


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Args:
        text: Text to copy

    Returns:
        True if successful, False otherwise
    """
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def format_plain(results: list[UploadResult]) -> str:
    """Format upload results as plain text URLs.

    Args:
        results: List of upload results

    Returns:
        Newline-separated URLs
    """
    return '\n'.join(r.url for r in results)


def format_markdown(results: list[UploadResult]) -> str:
    """Format upload results as Markdown image syntax.

    Args:
        results: List of upload results

    Returns:
        Markdown image tags with alt text
    """
    lines = []
    for r in results:
        alt = r.metadata.description if r.metadata else r.filename
        lines.append(f"![{alt}]({r.url})")
    return '\n'.join(lines)


def format_html(results: list[UploadResult]) -> str:
    """Format upload results as HTML img tags.

    Args:
        results: List of upload results

    Returns:
        HTML img tags with alt attributes
    """
    lines = []
    for r in results:
        alt = r.metadata.alt_text if r.metadata else r.filename
        lines.append(f'<img src="{r.url}" alt="{alt}">')
    return '\n'.join(lines)


def format_output(results: list[UploadResult], format_type: str) -> str:
    """Format upload results based on output format setting.

    Args:
        results: List of upload results
        format_type: Output format (plain, markdown, html)

    Returns:
        Formatted output string
    """
    formatters = {
        'plain': format_plain,
        'markdown': format_markdown,
        'html': format_html,
    }

    formatter = formatters.get(format_type, format_plain)
    return formatter(results)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_success(message: str) -> None:
    """Print a success message with checkmark.

    Args:
        message: Message to print
    """
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message with X mark.

    Args:
        message: Message to print
    """
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message with exclamation mark.

    Args:
        message: Message to print
    """
    console.print(f"[yellow]![/yellow] {message}")


def is_supported_image(path: Path) -> bool:
    """Check if file is a supported image format.

    Args:
        path: Path to file

    Returns:
        True if supported image format
    """
    return path.suffix.lower() in {
        '.jpg', '.jpeg', '.png', '.gif', '.webp',
        '.bmp', '.tiff', '.tif'
    }


def is_supported_video(path: Path) -> bool:
    """Check if file is a supported video format.

    Args:
        path: Path to file

    Returns:
        True if supported video format
    """
    return path.suffix.lower() in {'.mp4', '.mov', '.avi', '.webm'}


def is_supported_document(path: Path) -> bool:
    """Check if file is a supported document format.

    Args:
        path: Path to file

    Returns:
        True if supported document format
    """
    return path.suffix.lower() in {'.md', '.markdown', '.html', '.htm'}
