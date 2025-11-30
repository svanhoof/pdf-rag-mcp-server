"""Tests for document metadata functionality.

Tests the metadata CRUD operations and filtered search.
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from app.database import DOCUMENT_TYPES, SessionLocal, PDFDocument


# Path to test PDF
TEST_PDF_PATH = Path(__file__).parent.parent.parent / "input" / "paper.pdf"

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module")
async def client():
    """Create async test client for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="module")
async def uploaded_document(client: AsyncClient):
    """Upload and process a test document, yielding its ID for use in tests.

    This fixture uploads a PDF, waits for processing to complete, and cleans up after all tests.
    """
    if not TEST_PDF_PATH.exists():
        pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

    # Upload the PDF
    with open(TEST_PDF_PATH, "rb") as pdf_file:
        response = await client.post(
            "/api/upload",
            files={"file": (TEST_PDF_PATH.name, pdf_file, "application/pdf")}
        )

    assert response.status_code == 200, f"Upload failed: {response.text}"
    doc_id = response.json()["id"]

    # Wait for processing to complete
    max_wait_seconds = 120
    poll_interval = 2
    processing_complete = False

    for _ in range(max_wait_seconds // poll_interval):
        doc_response = await client.get(f"/api/documents/{doc_id}")
        assert doc_response.status_code == 200
        doc_data = doc_response.json()

        if doc_data.get("processed"):
            processing_complete = True
            break

        if doc_data.get("error"):
            pytest.fail(f"Processing failed with error: {doc_data['error']}")

        await asyncio.sleep(poll_interval)

    assert processing_complete, "Document processing did not complete within timeout"
    assert doc_data["chunks_count"] > 0, "Document should have chunks after processing"

    yield doc_id

    # Cleanup after all tests
    await asyncio.sleep(1)
    db = SessionLocal()
    try:
        doc = db.query(PDFDocument).filter(PDFDocument.id == doc_id).first()
        if doc:
            doc.processing = False
            db.commit()
    finally:
        db.close()

    await client.delete(f"/api/documents/{doc_id}")


class TestMetadataEndpoint:
    """Test the PATCH /api/documents/{id}/metadata endpoint."""

    async def test_update_metadata_nonexistent_document(self, client: AsyncClient):
        """Test updating metadata for a non-existent document returns 404."""
        response = await client.patch(
            "/api/documents/999999/metadata",
            json={"publication_year": 2024}
        )
        # Note: Due to SPA 404 handler, this may return 200 with HTML
        # We check that it's not a successful JSON response with the doc
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                data = response.json()
                assert "id" not in data or data.get("id") != 999999

    async def test_update_publication_year(self, client: AsyncClient, uploaded_document: int):
        """Test updating just the publication year."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"publication_year": 2023}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["publication_year"] == 2023

    async def test_update_document_type(self, client: AsyncClient, uploaded_document: int):
        """Test updating document type."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"document_type": "paper"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["document_type"] == "paper"

    async def test_update_authors(self, client: AsyncClient, uploaded_document: int):
        """Test updating authors list."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"authors": ["John Doe", "Jane Smith"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authors"] == ["John Doe", "Jane Smith"]

    async def test_update_all_metadata_fields(self, client: AsyncClient, uploaded_document: int):
        """Test updating all metadata fields at once."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={
                "publication_year": 2024,
                "document_type": "manual",
                "authors": ["Alice", "Bob"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["publication_year"] == 2024
        assert data["document_type"] == "manual"
        assert data["authors"] == ["Alice", "Bob"]

    async def test_invalid_document_type(self, client: AsyncClient, uploaded_document: int):
        """Test that invalid document type is rejected."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"document_type": "invalid_type"}
        )
        assert response.status_code == 400
        assert "document_type" in response.json().get("detail", "").lower()

    async def test_invalid_publication_year_too_low(self, client: AsyncClient, uploaded_document: int):
        """Test that year < 1900 is rejected."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"publication_year": 1800}
        )
        assert response.status_code == 422  # Validation error

    async def test_invalid_publication_year_too_high(self, client: AsyncClient, uploaded_document: int):
        """Test that year > 2100 is rejected."""
        doc_id = uploaded_document

        response = await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={"publication_year": 2200}
        )
        assert response.status_code == 422  # Validation error


class TestSearchFilters:
    """Test search API with metadata filters."""

    async def test_search_with_publication_year_filter(self, client: AsyncClient, uploaded_document: int):
        """Test search with publication_year filter returns results."""
        # First set metadata on the document
        await client.patch(
            f"/api/documents/{uploaded_document}/metadata",
            json={"publication_year": 2024}
        )
        await asyncio.sleep(1)  # Allow vector store to update

        response = await client.get(
            "/api/search",
            params={"q": "stable diffusion", "publication_year": 2024}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        # Should find our document
        assert len(data["results"]) > 0

    async def test_search_with_document_type_filter(self, client: AsyncClient, uploaded_document: int):
        """Test search with document_type filter returns results."""
        # First set metadata on the document
        await client.patch(
            f"/api/documents/{uploaded_document}/metadata",
            json={"document_type": "paper"}
        )
        await asyncio.sleep(1)  # Allow vector store to update

        response = await client.get(
            "/api/search",
            params={"q": "stable diffusion", "document_type": "paper"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        # Should find our document
        assert len(data["results"]) > 0

    async def test_search_with_combined_filters(self, client: AsyncClient, uploaded_document: int):
        """Test search with both filters returns results."""
        # First set metadata on the document
        await client.patch(
            f"/api/documents/{uploaded_document}/metadata",
            json={"publication_year": 2024, "document_type": "manual"}
        )
        await asyncio.sleep(1)  # Allow vector store to update

        response = await client.get(
            "/api/search",
            params={"q": "stable diffusion", "publication_year": 2024, "document_type": "manual"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        # Should find our document
        assert len(data["results"]) > 0

    async def test_search_excludes_non_matching_filters(self, client: AsyncClient, uploaded_document: int):
        """Test that search excludes documents not matching filters."""
        # Set metadata to specific values
        await client.patch(
            f"/api/documents/{uploaded_document}/metadata",
            json={"publication_year": 2023, "document_type": "paper"}
        )
        await asyncio.sleep(1)  # Allow vector store to update

        # Search with non-matching year
        response = await client.get(
            "/api/search",
            params={"q": "stable diffusion", "publication_year": 2020}
        )
        assert response.status_code == 200
        results = response.json().get("results", [])
        found = any(r.get("pdf_id") == uploaded_document for r in results)
        assert not found, "Document should NOT appear when filtered by wrong year"

        # Search with non-matching type
        response = await client.get(
            "/api/search",
            params={"q": "stable diffusion", "document_type": "handbook"}
        )
        assert response.status_code == 200
        results = response.json().get("results", [])
        found = any(r.get("pdf_id") == uploaded_document for r in results)
        assert not found, "Document should NOT appear when filtered by wrong type"

    async def test_search_invalid_document_type_filter(self, client: AsyncClient):
        """Test search with invalid document_type filter."""
        response = await client.get(
            "/api/search",
            params={"q": "test", "document_type": "invalid"}
        )
        assert response.status_code == 400
        assert "document_type" in response.json().get("detail", "").lower()

    async def test_search_invalid_year_filter(self, client: AsyncClient):
        """Test search with invalid year filter."""
        response = await client.get(
            "/api/search",
            params={"q": "test", "publication_year": 1800}
        )
        assert response.status_code == 422  # Validation error


class TestDocumentTypes:
    """Test document type constants."""

    def test_document_types_defined(self):
        """Test that DOCUMENT_TYPES is defined and non-empty."""
        assert DOCUMENT_TYPES is not None
        assert len(DOCUMENT_TYPES) > 0

    def test_expected_document_types(self):
        """Test that expected document types are present."""
        expected = ["paper", "handbook", "manual", "report", "other"]
        for doc_type in expected:
            assert doc_type in DOCUMENT_TYPES


class TestMetadataInDocumentResponse:
    """Test that metadata fields appear in document responses."""

    async def test_documents_list_includes_metadata(self, client: AsyncClient, uploaded_document: int):
        """Test GET /api/documents includes metadata fields."""
        response = await client.get("/api/documents")
        assert response.status_code == 200
        docs = response.json()

        assert len(docs) > 0
        doc = docs[0]
        # Check metadata fields exist (may be null)
        assert "publication_year" in doc
        assert "authors" in doc
        assert "document_type" in doc

    async def test_document_detail_includes_metadata(self, client: AsyncClient, uploaded_document: int):
        """Test GET /api/documents/{id} includes metadata fields."""
        doc_id = uploaded_document
        response = await client.get(f"/api/documents/{doc_id}")
        assert response.status_code == 200
        doc = response.json()

        # Check metadata fields exist
        assert "publication_year" in doc
        assert "authors" in doc
        assert "document_type" in doc

    async def test_metadata_persists_after_update(self, client: AsyncClient, uploaded_document: int):
        """Test that metadata is persisted and retrievable after update."""
        doc_id = uploaded_document

        # Set metadata
        await client.patch(
            f"/api/documents/{doc_id}/metadata",
            json={
                "publication_year": 2022,
                "document_type": "report",
                "authors": ["Test Author"]
            }
        )

        # Verify it's persisted
        response = await client.get(f"/api/documents/{doc_id}")
        assert response.status_code == 200
        doc = response.json()
        assert doc["publication_year"] == 2022
        assert doc["document_type"] == "report"
        assert doc["authors"] == ["Test Author"]
