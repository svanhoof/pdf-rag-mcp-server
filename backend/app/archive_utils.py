"""Archive file utilities for structured naming convention.

This module provides utilities for naming and renaming archive files
according to the convention: <first_author>_<year>_<title>.pdf
"""

import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger("archive_utils")

# Archive directory - can be overridden by environment variable
ARCHIVE_DIR = os.getenv("PDF_RAG_ARCHIVE_DIR", "./archive")


def sanitize_filename(text: str) -> str:
    """Sanitize a string to be safe for use in a filename.

    Replaces unsafe characters with underscores and collapses multiple underscores.
    """
    if not text:
        return ""
    # Replace common unsafe characters with underscore
    unsafe_chars = r'<>:"/\|?*'
    result = text
    for char in unsafe_chars:
        result = result.replace(char, "_")
    # Replace whitespace sequences with single underscore
    result = re.sub(r'\s+', '_', result)
    # Collapse multiple underscores
    result = re.sub(r'_+', '_', result)
    # Remove leading/trailing underscores
    result = result.strip('_')
    # Limit length (leave room for author_year_ prefix)
    max_len = 150
    if len(result) > max_len:
        result = result[:max_len].rstrip('_')
    return result


def build_structured_archive_filename(
    first_author: str | None,
    year: int | None,
    title: str | None,
    fallback_filename: str,
) -> str:
    """Build a structured archive filename: <first_author>_<year>_<title>.pdf

    Falls back to the original filename if insufficient metadata is available.
    """
    parts = []

    # Extract first author's last name if available
    if first_author:
        # Take last name (assume "First Last" or "Last, First" format)
        author_clean = first_author.strip()
        if ',' in author_clean:
            # "Last, First" format
            last_name = author_clean.split(',')[0].strip()
        else:
            # "First Last" format - take last word
            words = author_clean.split()
            last_name = words[-1] if words else ""
        if last_name:
            parts.append(sanitize_filename(last_name))

    # Add year
    if year:
        parts.append(str(year))

    # Add title
    if title:
        parts.append(sanitize_filename(title))

    # Build filename or fall back
    if parts:
        structured_name = "_".join(parts) + ".pdf"
        return structured_name

    # Fallback to original filename
    return fallback_filename


def get_unique_archive_path(
    original_filename: str,
    first_author: str | None = None,
    year: int | None = None,
    title: str | None = None,
    exclude_path: str | None = None,
) -> str:
    """Generate a unique archive path using structured naming convention.

    Format: <first_author>_<year>_<title>.pdf
    Falls back to original filename if metadata is not available.
    Adds numeric suffix if file exists.

    Args:
        original_filename: Fallback filename if no metadata available.
        first_author: First author's name for structured naming.
        year: Publication year for structured naming.
        title: Document title for structured naming.
        exclude_path: Path to exclude from collision checks (used when renaming existing file).
    """
    target_filename = build_structured_archive_filename(
        first_author=first_author,
        year=year,
        title=title,
        fallback_filename=original_filename,
    )

    base_path = Path(ARCHIVE_DIR) / target_filename

    # If the target path is the same as the excluded path, it's not a collision
    if exclude_path and str(base_path) == exclude_path:
        return str(base_path)

    if not base_path.exists():
        return str(base_path)

    # File exists, add numeric suffix
    stem = base_path.stem
    suffix = base_path.suffix
    counter = 1
    while True:
        new_path = Path(ARCHIVE_DIR) / f"{stem}({counter}){suffix}"
        # Skip if this is the excluded path
        if exclude_path and str(new_path) == exclude_path:
            return str(new_path)
        if not new_path.exists():
            return str(new_path)
        counter += 1


def rename_archive_for_document(
    archive_path: str | None,
    filename: str,
    first_author: str | None = None,
    year: int | None = None,
    title: str | None = None,
) -> str | None:
    """Rename the archive file to match structured naming convention.

    Returns the new archive path if renamed, None if no change needed or no archive exists.

    Args:
        archive_path: Current path to the archive file.
        filename: Original document filename (used as fallback).
        first_author: First author's name for structured naming.
        year: Publication year for structured naming.
        title: Document title for structured naming.
    """
    if not archive_path or not os.path.exists(archive_path):
        return None

    new_path = get_unique_archive_path(
        original_filename=filename,
        first_author=first_author,
        year=year,
        title=title,
        exclude_path=archive_path,
    )

    # If the path hasn't changed, no need to rename
    if new_path == archive_path:
        return None

    try:
        shutil.move(archive_path, new_path)
        logger.info(f"Renamed archive file from {archive_path} to {new_path}")
        return new_path
    except Exception as e:
        logger.error(f"Failed to rename archive file: {e}")
        return None
