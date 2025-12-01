"""Tests for structured archive naming functionality.

Tests the archive file naming convention: <first_author>_<year>_<title>.pdf
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.archive_utils import (
    build_structured_archive_filename,
    get_unique_archive_path,
    rename_archive_for_document,
    sanitize_filename,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_empty_string(self):
        """Test with empty string."""
        assert sanitize_filename("") == ""

    def test_simple_text(self):
        """Test with simple text."""
        assert sanitize_filename("hello world") == "hello_world"

    def test_unsafe_characters(self):
        """Test removal of unsafe characters."""
        assert sanitize_filename('file<>:"/\\|?*name') == "file_name"

    def test_multiple_spaces(self):
        """Test collapsing multiple spaces."""
        assert sanitize_filename("hello   world") == "hello_world"

    def test_multiple_underscores(self):
        """Test collapsing multiple underscores."""
        assert sanitize_filename("hello___world") == "hello_world"

    def test_leading_trailing_underscores(self):
        """Test stripping leading and trailing underscores."""
        assert sanitize_filename("_hello_world_") == "hello_world"

    def test_long_text(self):
        """Test truncation of long text."""
        long_text = "a" * 200
        result = sanitize_filename(long_text)
        assert len(result) <= 150

    def test_special_characters_in_title(self):
        """Test with realistic title containing special characters."""
        title = "High-Resolution Image Synthesis: A New Approach"
        result = sanitize_filename(title)
        assert result == "High-Resolution_Image_Synthesis_A_New_Approach"


class TestBuildStructuredArchiveFilename:
    """Tests for build_structured_archive_filename function."""

    def test_all_metadata_provided(self):
        """Test with all metadata provided."""
        result = build_structured_archive_filename(
            first_author="John Smith",
            year=2023,
            title="Machine Learning for Beginners",
            fallback_filename="original.pdf",
        )
        assert result == "Smith_2023_Machine_Learning_for_Beginners.pdf"

    def test_last_first_author_format(self):
        """Test with 'Last, First' author format."""
        result = build_structured_archive_filename(
            first_author="Smith, John",
            year=2023,
            title="Test Title",
            fallback_filename="original.pdf",
        )
        assert result == "Smith_2023_Test_Title.pdf"

    def test_only_author(self):
        """Test with only author provided."""
        result = build_structured_archive_filename(
            first_author="John Smith",
            year=None,
            title=None,
            fallback_filename="original.pdf",
        )
        assert result == "Smith.pdf"

    def test_only_year(self):
        """Test with only year provided."""
        result = build_structured_archive_filename(
            first_author=None,
            year=2023,
            title=None,
            fallback_filename="original.pdf",
        )
        assert result == "2023.pdf"

    def test_only_title(self):
        """Test with only title provided."""
        result = build_structured_archive_filename(
            first_author=None,
            year=None,
            title="Test Title",
            fallback_filename="original.pdf",
        )
        assert result == "Test_Title.pdf"

    def test_author_and_year(self):
        """Test with author and year, no title."""
        result = build_structured_archive_filename(
            first_author="John Smith",
            year=2023,
            title=None,
            fallback_filename="original.pdf",
        )
        assert result == "Smith_2023.pdf"

    def test_year_and_title(self):
        """Test with year and title, no author."""
        result = build_structured_archive_filename(
            first_author=None,
            year=2023,
            title="Test Title",
            fallback_filename="original.pdf",
        )
        assert result == "2023_Test_Title.pdf"

    def test_no_metadata(self):
        """Test fallback when no metadata provided."""
        result = build_structured_archive_filename(
            first_author=None,
            year=None,
            title=None,
            fallback_filename="original.pdf",
        )
        assert result == "original.pdf"

    def test_empty_author(self):
        """Test with empty author string."""
        result = build_structured_archive_filename(
            first_author="",
            year=2023,
            title="Test Title",
            fallback_filename="original.pdf",
        )
        assert result == "2023_Test_Title.pdf"

    def test_whitespace_author(self):
        """Test with whitespace-only author."""
        result = build_structured_archive_filename(
            first_author="   ",
            year=2023,
            title="Test Title",
            fallback_filename="original.pdf",
        )
        assert result == "2023_Test_Title.pdf"


class TestGetUniqueArchivePath:
    """Tests for get_unique_archive_path function."""

    def test_no_collision(self):
        """Test when target path doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                result = get_unique_archive_path(
                    original_filename="test.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )
                assert result == os.path.join(tmpdir, "Smith_2023_Test_Title.pdf")

    def test_with_collision(self):
        """Test when target path already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file
            existing = Path(tmpdir) / "Smith_2023_Test_Title.pdf"
            existing.touch()

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                result = get_unique_archive_path(
                    original_filename="test.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )
                assert result == os.path.join(tmpdir, "Smith_2023_Test_Title(1).pdf")

    def test_with_multiple_collisions(self):
        """Test when multiple colliding files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing files
            (Path(tmpdir) / "Smith_2023_Test_Title.pdf").touch()
            (Path(tmpdir) / "Smith_2023_Test_Title(1).pdf").touch()
            (Path(tmpdir) / "Smith_2023_Test_Title(2).pdf").touch()

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                result = get_unique_archive_path(
                    original_filename="test.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )
                assert result == os.path.join(tmpdir, "Smith_2023_Test_Title(3).pdf")

    def test_exclude_path_no_change_needed(self):
        """Test exclude_path when target is same as excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "Smith_2023_Test_Title.pdf")
            # Create the file
            Path(target).touch()

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                result = get_unique_archive_path(
                    original_filename="test.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                    exclude_path=target,
                )
                # Should return the same path since it's excluded
                assert result == target

    def test_fallback_to_original(self):
        """Test fallback to original filename when no metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                result = get_unique_archive_path(
                    original_filename="my_document.pdf",
                )
                assert result == os.path.join(tmpdir, "my_document.pdf")


class TestRenameArchiveForDocument:
    """Tests for rename_archive_for_document function."""

    def test_rename_with_metadata(self):
        """Test renaming archive file with metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create original archive file
            original_path = os.path.join(tmpdir, "original_file.pdf")
            with open(original_path, "w") as f:
                f.write("test content")

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="original_file.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )

                expected_path = os.path.join(tmpdir, "Smith_2023_Test_Title.pdf")
                assert new_path == expected_path
                assert os.path.exists(expected_path)
                assert not os.path.exists(original_path)

    def test_no_rename_when_no_metadata(self):
        """Test that no rename happens when no metadata provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create original archive file
            original_path = os.path.join(tmpdir, "original_file.pdf")
            with open(original_path, "w") as f:
                f.write("test content")

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="original_file.pdf",
                )

                # Should return None since no change needed
                assert new_path is None
                assert os.path.exists(original_path)

    def test_no_archive_file(self):
        """Test handling when archive file doesn't exist."""
        new_path = rename_archive_for_document(
            archive_path="/nonexistent/path.pdf",
            filename="test.pdf",
            first_author="John Smith",
            year=2023,
            title="Test Title",
        )
        assert new_path is None

    def test_none_archive_path(self):
        """Test handling when archive_path is None."""
        new_path = rename_archive_for_document(
            archive_path=None,
            filename="test.pdf",
            first_author="John Smith",
            year=2023,
            title="Test Title",
        )
        assert new_path is None

    def test_rename_preserves_content(self):
        """Test that file content is preserved after rename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create original archive file with specific content
            original_path = os.path.join(tmpdir, "original_file.pdf")
            test_content = b"PDF file content here\x00\x01\x02"
            with open(original_path, "wb") as f:
                f.write(test_content)

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="original_file.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )

                assert new_path is not None
                with open(new_path, "rb") as f:
                    assert f.read() == test_content

    def test_rename_with_collision(self):
        """Test renaming when target already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create existing file at target location
            existing_path = os.path.join(tmpdir, "Smith_2023_Test_Title.pdf")
            with open(existing_path, "w") as f:
                f.write("existing content")

            # Create original archive file
            original_path = os.path.join(tmpdir, "original_file.pdf")
            with open(original_path, "w") as f:
                f.write("new content")

            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="original_file.pdf",
                    first_author="John Smith",
                    year=2023,
                    title="Test Title",
                )

                expected_path = os.path.join(tmpdir, "Smith_2023_Test_Title(1).pdf")
                assert new_path == expected_path
                assert os.path.exists(expected_path)
                assert os.path.exists(existing_path)  # Original still exists
                assert not os.path.exists(original_path)


class TestRealWorldScenarios:
    """Tests simulating real-world usage scenarios."""

    def test_upload_then_metadata_update(self):
        """Test the flow: upload -> metadata extraction -> manual update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                # Step 1: Upload - file saved with original name
                original_path = os.path.join(tmpdir, "document123.pdf")
                with open(original_path, "w") as f:
                    f.write("PDF content")

                # Step 2: Metadata extracted by LLM
                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="document123.pdf",
                    first_author="Alice Brown",
                    year=2024,
                    title="Deep Learning Advances",
                )

                assert new_path == os.path.join(tmpdir, "Brown_2024_Deep_Learning_Advances.pdf")
                assert os.path.exists(new_path)

                # Step 3: User manually updates year
                updated_path = rename_archive_for_document(
                    archive_path=new_path,
                    filename="document123.pdf",
                    first_author="Alice Brown",
                    year=2025,  # Changed year
                    title="Deep Learning Advances",
                )

                assert updated_path == os.path.join(tmpdir, "Brown_2025_Deep_Learning_Advances.pdf")
                assert os.path.exists(updated_path)
                assert not os.path.exists(new_path)

    def test_author_name_formats(self):
        """Test various author name formats."""
        test_cases = [
            ("John Smith", "Smith"),
            ("Smith, John", "Smith"),
            ("J. Robert Smith", "Smith"),
            ("Smith", "Smith"),
            ("John van der Berg", "Berg"),  # Multi-word last name
        ]

        for author_name, expected_last in test_cases:
            result = build_structured_archive_filename(
                first_author=author_name,
                year=2023,
                title="Test",
                fallback_filename="fallback.pdf",
            )
            assert result.startswith(f"{expected_last}_2023"), f"Failed for author: {author_name}"

    def test_title_with_special_characters(self):
        """Test handling of titles with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.archive_utils.ARCHIVE_DIR", tmpdir):
                original_path = os.path.join(tmpdir, "paper.pdf")
                with open(original_path, "w") as f:
                    f.write("content")

                new_path = rename_archive_for_document(
                    archive_path=original_path,
                    filename="paper.pdf",
                    first_author="John Smith",
                    year=2023,
                    title='Research: A "Novel" Approach (Part 1/3)',
                )

                # Should sanitize special characters
                assert new_path is not None
                filename = os.path.basename(new_path)
                assert '"' not in filename
                assert ':' not in filename
                assert '/' not in filename
