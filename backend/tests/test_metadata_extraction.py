"""Tests for automatic metadata extraction from PDF documents.

Tests the LLM-based metadata extraction functionality.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file from project root to get ANTHROPIC_API_KEY
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from app.metadata_extractor import (
    DocumentMetadata,
    extract_metadata_from_pdf,
    extract_metadata_with_llm,
    extract_text_from_first_pages,
    parse_llm_response,
)

# Path to test PDF
TEST_PDF_PATH = Path(__file__).parent.parent.parent / "input" / "paper.pdf"


class TestExtractTextFromFirstPages:
    """Tests for extract_text_from_first_pages function."""

    def test_extract_text_from_existing_pdf(self):
        """Test text extraction from a real PDF."""
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        text = extract_text_from_first_pages(str(TEST_PDF_PATH), num_pages=3)

        assert text, "Should extract some text from the PDF"
        assert "Page 1" in text, "Should include page markers"
        assert len(text) > 100, "Should extract substantial text"

    def test_extract_limited_pages(self):
        """Test that num_pages parameter limits extraction."""
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        text_1_page = extract_text_from_first_pages(str(TEST_PDF_PATH), num_pages=1)
        text_3_pages = extract_text_from_first_pages(str(TEST_PDF_PATH), num_pages=3)

        # 3 pages should have more content than 1 page
        assert len(text_3_pages) >= len(text_1_page)


class TestParseLLMResponse:
    """Tests for parse_llm_response function."""

    def test_parse_complete_response(self):
        """Test parsing a complete LLM response."""
        response = """AUTHORS: John Doe, Jane Smith
YEAR: 2023
TYPE: paper"""

        metadata = parse_llm_response(response)

        assert metadata.authors == ["John Doe", "Jane Smith"]
        assert metadata.publication_year == 2023
        assert metadata.document_type == "paper"

    def test_parse_response_with_unknown_authors(self):
        """Test parsing when authors are unknown."""
        response = """AUTHORS: Unknown
YEAR: 2022
TYPE: report"""

        metadata = parse_llm_response(response)

        assert metadata.authors == []
        assert metadata.publication_year == 2022
        assert metadata.document_type == "report"

    def test_parse_response_with_unknown_year(self):
        """Test parsing when year is unknown."""
        response = """AUTHORS: Alice Brown
YEAR: Unknown
TYPE: manual"""

        metadata = parse_llm_response(response)

        assert metadata.authors == ["Alice Brown"]
        assert metadata.publication_year is None
        assert metadata.document_type == "manual"

    def test_parse_response_with_invalid_year(self):
        """Test parsing when year is invalid."""
        response = """AUTHORS: Test Author
YEAR: invalid
TYPE: paper"""

        metadata = parse_llm_response(response)

        assert metadata.publication_year is None

    def test_parse_response_with_year_out_of_range(self):
        """Test parsing when year is out of valid range."""
        response = """AUTHORS: Test Author
YEAR: 1800
TYPE: paper"""

        metadata = parse_llm_response(response)

        assert metadata.publication_year is None

    def test_parse_response_invalid_document_type(self):
        """Test parsing when document type is not in allowed list."""
        response = """AUTHORS: Test Author
YEAR: 2023
TYPE: novel"""

        metadata = parse_llm_response(response)

        # Invalid types should default to "other"
        assert metadata.document_type == "other"

    def test_parse_response_case_insensitive(self):
        """Test that parsing is case-insensitive for labels."""
        response = """authors: John Doe
year: 2021
type: handbook"""

        metadata = parse_llm_response(response)

        assert metadata.authors == ["John Doe"]
        assert metadata.publication_year == 2021
        assert metadata.document_type == "handbook"


class TestDocumentMetadata:
    """Tests for DocumentMetadata dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = DocumentMetadata(
            title="Test Document Title",
            authors=["Author One", "Author Two"],
            publication_year=2024,
            document_type="paper",
        )

        result = metadata.to_dict()

        assert result == {
            "title": "Test Document Title",
            "authors": ["Author One", "Author Two"],
            "publication_year": 2024,
            "document_type": "paper",
        }

    def test_to_dict_with_none_values(self):
        """Test conversion to dictionary with None values."""
        metadata = DocumentMetadata(
            title=None,
            authors=[],
            publication_year=None,
            document_type=None,
        )

        result = metadata.to_dict()

        assert result == {
            "title": None,
            "authors": [],
            "publication_year": None,
            "document_type": None,
        }


class TestExtractMetadataWithLLM:
    """Tests for extract_metadata_with_llm function."""

    def test_raises_without_api_key(self):
        """Test that function raises error when API key is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            os.environ.pop("ANTHROPIC_API_KEY", None)

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                extract_metadata_with_llm("Some document text")

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set - skipping live LLM test",
    )
    def test_extract_metadata_live(self):
        """Test actual LLM metadata extraction (requires API key)."""
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        text = extract_text_from_first_pages(str(TEST_PDF_PATH), num_pages=3)
        metadata = extract_metadata_with_llm(text)

        # The metadata should be a valid DocumentMetadata object
        assert isinstance(metadata, DocumentMetadata)
        assert isinstance(metadata.authors, list)
        assert metadata.publication_year is None or isinstance(metadata.publication_year, int)
        assert metadata.document_type is None or metadata.document_type in [
            "paper", "handbook", "manual", "report", "other"
        ]


class TestExtractMetadataFromPDF:
    """Tests for the main extract_metadata_from_pdf function."""

    def test_raises_for_nonexistent_file(self):
        """Test that function raises error for non-existent PDF."""
        with pytest.raises(FileNotFoundError):
            extract_metadata_from_pdf("/path/to/nonexistent.pdf")

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set - skipping live LLM test",
    )
    def test_extract_from_real_pdf(self):
        """Test full extraction pipeline on a real PDF (requires API key)."""
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        metadata = extract_metadata_from_pdf(str(TEST_PDF_PATH))

        # Check that we got a valid result
        assert isinstance(metadata, DocumentMetadata)
        assert isinstance(metadata.authors, list)

        # Print extracted metadata for visibility
        print(f"\nExtracted metadata from {TEST_PDF_PATH.name}:")
        print(f"  Authors: {metadata.authors}")
        print(f"  Year: {metadata.publication_year}")
        print(f"  Type: {metadata.document_type}")

    def test_extract_with_mocked_llm(self):
        """Test extraction with a mocked LLM response."""
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        mock_response = MagicMock()
        mock_response.content = """AUTHORS: Robin Rombach, Andreas Blattmann
YEAR: 2022
TYPE: paper"""

        with patch("langchain_anthropic.ChatAnthropic") as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_llm_class.return_value = mock_llm

            # Set a dummy API key for the test
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                metadata = extract_metadata_from_pdf(str(TEST_PDF_PATH))

        assert metadata.authors == ["Robin Rombach", "Andreas Blattmann"]
        assert metadata.publication_year == 2022
        assert metadata.document_type == "paper"


class TestIntegration:
    """Integration tests that run the full pipeline."""

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set - skipping live integration test",
    )
    def test_full_pipeline_with_sample_pdf(self):
        """Full integration test with the sample PDF and real LLM.

        This test verifies that:
        1. We can extract text from the sample PDF
        2. The LLM can process the text and return metadata
        3. The metadata is in the expected format
        """
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        # Run the full extraction
        metadata = extract_metadata_from_pdf(str(TEST_PDF_PATH))

        # Verify structure
        assert isinstance(metadata, DocumentMetadata)
        assert isinstance(metadata.authors, list)

        # Verify types are correct
        if metadata.publication_year is not None:
            assert isinstance(metadata.publication_year, int)
            assert 1900 <= metadata.publication_year <= 2100

        if metadata.document_type is not None:
            assert metadata.document_type in ["paper", "handbook", "manual", "report", "other"]

        # Log results for manual verification
        print("\n" + "=" * 60)
        print("INTEGRATION TEST RESULTS")
        print("=" * 60)
        print(f"PDF: {TEST_PDF_PATH.name}")
        print(f"Authors: {metadata.authors}")
        print(f"Publication Year: {metadata.publication_year}")
        print(f"Document Type: {metadata.document_type}")
        print("=" * 60)
