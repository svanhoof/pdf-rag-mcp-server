# Plan: Document Metadata for Scoped Search

## Overview

Add document-level metadata (year of publication, authors, document type) to enable filtered/scoped semantic search. This plan covers database schema changes, API modifications, vector store updates, frontend UI for editing metadata, and search filtering.

## Current State

- Documents only have basic metadata: filename, file_size, uploaded_at, page_count, chunks_count
- Search queries all documents equally with no filtering capability
- Vector store chunks include `pdf_id` but no document-level metadata for filtering

## Target State

- Each document can have:
  - `publication_year` (Integer, nullable) - e.g., 2023
  - `authors` (JSON array of strings, nullable) - e.g., ["John Doe", "Jane Smith"]
  - `document_type` (String enum, nullable) - "paper", "handbook", "manual", "report", "other"
- Search API accepts optional filters to scope results
- Frontend provides UI to view/edit document metadata
- Vector store supports filtered queries

---

## Implementation Steps

### Phase 0: Baseline Unit Tests (Before Any Changes)

**File: `backend/tests/test_baseline.py` (new)**

Create baseline tests for existing functionality to ensure we don't break anything during implementation.

Using pytest with httpx for async API testing. Test sample: `input/IMAGE_GENERATION_WITH_STABLE_DIFFUSION_AI.pdf`

1. **Test fixtures:**
   - Fresh database and vector store setup/teardown
   - Async client for FastAPI app

2. **End-to-End Test: `test_upload_process_search`**

   Single comprehensive test that covers the full document lifecycle:
   ```python
   async def test_upload_process_search():
       # 1. Upload the sample PDF
       response = await client.post("/api/upload", files={"file": pdf_file})
       assert response.status_code == 200
       doc_id = response.json()["id"]

       # 2. Wait for processing to complete (poll with timeout)
       for _ in range(60):  # max 60 seconds
           doc = await client.get(f"/api/documents/{doc_id}")
           if doc.json()["processed"]:
               break
           await asyncio.sleep(1)
       assert doc.json()["processed"] == True
       assert doc.json()["chunks_count"] > 0

       # 3. Search for content from the PDF
       search = await client.get("/api/search", params={"q": "stable diffusion"})
       assert search.status_code == 200
       results = search.json()["results"]
       assert len(results) > 0
       assert results[0]["pdf_id"] == doc_id

       # 4. Cleanup - delete document
       delete = await client.delete(f"/api/documents/{doc_id}")
       assert delete.status_code == 200
   ```

**Running Baseline Tests:**
```bash
cd backend
pytest tests/test_baseline.py -v
```

This establishes a safety net before making any schema or API changes.

---

### Phase 1: Database Schema Changes

**File: `backend/app/database.py`**

1. Add new columns to `PDFDocument` model:
   ```python
   publication_year = Column(Integer, nullable=True)
   authors = Column(JSON, nullable=True)  # List of strings
   document_type = Column(String, nullable=True)  # "paper", "handbook", "manual", "report", "other"
   ```

2. Add document type enum for validation:
   ```python
   DOCUMENT_TYPES = ["paper", "handbook", "manual", "report", "other"]
   ```

---

### Phase 2: API Endpoints

**File: `backend/app/main.py`**

1. **New endpoint: Update document metadata**
   ```
   PATCH /api/documents/{doc_id}/metadata
   Body: {
     "publication_year": 2023,
     "authors": ["Author 1", "Author 2"],
     "document_type": "paper"
   }
   ```
   - Validates document_type against allowed enum values
   - Validates publication_year is reasonable (e.g., 1900-2100)
   - Authors must be array of non-empty strings

2. **Modify GET /api/documents/{doc_id}**
   - Include new metadata fields in response

3. **Modify GET /api/documents list**
   - Include new metadata fields in each document

4. **Modify search endpoints (GET /api/search and /mcp/v1/query)**
   - Add optional query parameters:
     - `year_from` (int) - minimum publication year
     - `year_to` (int) - maximum publication year
     - `authors` (string, comma-separated) - filter by author names (partial match)
     - `document_type` (string) - filter by exact type
   - Filters are ANDed together

---

### Phase 3: Vector Store Updates

**File: `backend/app/vector_store.py` and `backend/app/vector_backends/lance_backend.py`**

1. **Metadata propagation to chunks**
   - When storing chunks, include document-level metadata:
     ```python
     {
       ...existing fields...,
       "publication_year": doc.publication_year,
       "authors": doc.authors,  # JSON serialized
       "document_type": doc.document_type
     }
     ```

2. **Filtered search implementation**
   - LanceDB supports SQL-like `where` clauses:
     ```python
     table.search(query_vector)
          .where("publication_year >= 2020 AND document_type = 'paper'")
          .limit(k)
     ```

3. **Metadata refresh mechanism**
   - When document metadata is updated via API, update all associated chunks in vector store
   - Add method: `update_document_metadata(pdf_id, metadata_dict)`

---

### Phase 4: Frontend - Document Metadata Editor

**File: `frontend/src/components/DocumentMetadataEditor.jsx` (new)**

1. Create modal component for editing document metadata:
   - Year input (number field, optional)
   - Authors input (tag-style input for adding/removing authors)
   - Document type dropdown (paper, handbook, manual, report, other)
   - Save/Cancel buttons

**File: `frontend/src/components/FileList.jsx`**

1. **Add new columns to the document table:**
   - "Year" column - displays publication_year (or "-" if not set)
   - "Type" column - displays document_type with badge styling
   - "Authors" column - displays comma-separated list or count (e.g., "2 authors")

2. **Add "Edit" button in the actions column:**
   - Pencil icon button next to existing Delete/View actions
   - Opens DocumentMetadataEditor modal
   - On save, refreshes the document list

3. **Responsive handling:**
   - On mobile cards: show metadata as additional rows/badges
   - On desktop table: show as dedicated columns

---

### Phase 5: Frontend - Search Filters

**File: `frontend/src/pages/Search.jsx`**

1. Add filter controls above search input:
   - Year range (from/to number inputs)
   - Document type multiselect or dropdown
   - Authors text input (for partial matching)

2. Pass filters to search API call:
   ```javascript
   searchDocuments({
     query,
     limit,
     offset,
     year_from,
     year_to,
     document_type,
     authors
   })
   ```

3. Display active filters as pills/tags with clear buttons

**File: `frontend/src/api/documents.js`**

1. Update `searchDocuments` function to accept filter parameters

---

### Phase 6: MCP Query Updates

**File: `backend/app/main.py` (MCP routes)**

1. **Add filter parameters to MCP query endpoint (`/mcp/v1/query`)**
   - Same filter parameters as HTTP search:
     - `year_from` (int) - minimum publication year
     - `year_to` (int) - maximum publication year
     - `authors` (string) - comma-separated author names for partial match
     - `document_type` (string) - filter by exact type

2. **Ensure consistency between HTTP and MCP APIs**
   - Both endpoints use the same underlying search logic
   - Filter validation is shared (reusable Pydantic models)
   - AI tools (Cursor, etc.) can leverage full filtering capability

---

### Phase 7: Unit Tests

**File: `backend/tests/test_metadata.py` (new)**

Using pytest with httpx for async API testing. Test sample: `input/IMAGE_GENERATION_WITH_STABLE_DIFFUSION_AI.pdf`

1. **Test fixtures:**
   - Fresh database setup/teardown
   - Test PDF upload fixture
   - Sample metadata:
     ```python
     TEST_METADATA = {
         "publication_year": 2023,
         "authors": ["Smith, John", "Doe, Jane"],
         "document_type": "paper"
     }
     ```

2. **API Tests:**
   - `test_upload_pdf` - Upload sample PDF, verify document created
   - `test_update_metadata` - PATCH metadata, verify response
   - `test_get_document_with_metadata` - GET document includes metadata fields
   - `test_list_documents_with_metadata` - GET /api/documents includes metadata
   - `test_metadata_validation_invalid_year` - Reject year outside 1900-2100
   - `test_metadata_validation_invalid_type` - Reject unknown document_type
   - `test_metadata_validation_invalid_authors` - Reject non-array authors

3. **Search Filter Tests:**
   - `test_search_no_filter` - Search works without filters (backwards compatible)
   - `test_search_filter_by_year_from` - Only returns docs >= year
   - `test_search_filter_by_year_to` - Only returns docs <= year
   - `test_search_filter_by_year_range` - Combines year_from and year_to
   - `test_search_filter_by_document_type` - Exact match on type
   - `test_search_filter_by_author` - Partial match on author name
   - `test_search_filter_combined` - Multiple filters ANDed together
   - `test_search_filter_no_match` - Returns empty when no docs match filters

4. **Vector Store Tests:**
   - `test_metadata_stored_in_chunks` - Verify chunks include document metadata
   - `test_metadata_update_propagates_to_chunks` - Update refreshes chunk metadata

**Running Tests:**
```bash
cd backend
pytest tests/test_metadata.py -v
```

---

## API Schema Summary

### PATCH /api/documents/{doc_id}/metadata

**Request:**
```json
{
  "publication_year": 2023,
  "authors": ["John Doe", "Jane Smith"],
  "document_type": "paper"
}
```

**Response:**
```json
{
  "id": 1,
  "filename": "example.pdf",
  "publication_year": 2023,
  "authors": ["John Doe", "Jane Smith"],
  "document_type": "paper",
  ...other existing fields...
}
```

### GET /api/search (updated)

**Query Parameters:**
- `q` (required) - search query
- `limit` (optional, default 10)
- `offset` (optional, default 0)
- `year_from` (optional) - min publication year
- `year_to` (optional) - max publication year
- `document_type` (optional) - filter by type
- `authors` (optional) - comma-separated author names for partial match

---

## File Changes Summary

| File | Changes |
|------|---------|
| `backend/app/database.py` | Add 3 new columns to PDFDocument |
| `backend/app/main.py` | New PATCH endpoint, update GET endpoints, add search filters |
| `backend/app/vector_store.py` | Add metadata update method, pass metadata to backend |
| `backend/app/vector_backends/lance_backend.py` | Add metadata fields to schema, implement filtered search |
| `backend/app/vector_backends/chroma_backend.py` | Same changes for Chroma compatibility |
| `backend/app/pdf_processor.py` | Include document metadata when storing chunks |
| `frontend/src/components/DocumentMetadataEditor.jsx` | New component |
| `frontend/src/components/FileList.jsx` | Add metadata display and edit button |
| `frontend/src/pages/Search.jsx` | Add filter controls |
| `frontend/src/api/documents.js` | Update API functions |
| `backend/tests/test_baseline.py` | Baseline functional test (Phase 0) |
| `backend/tests/test_metadata.py` | Metadata and filter tests (Phase 7) |

---

## Migration Strategy

No migration needed - existing database can be deleted and recreated with new schema.

---

## Testing Checklist

- [ ] PATCH endpoint validates inputs correctly
- [ ] GET endpoints return new metadata fields
- [ ] Search with no filters works as before
- [ ] Search with year filter returns correct results
- [ ] Search with type filter returns correct results
- [ ] Search with author filter returns correct results
- [ ] Combined filters work correctly (AND logic)
- [ ] Frontend metadata editor saves correctly
- [ ] Frontend search filters work correctly
- [ ] MCP query with filters works correctly
- [ ] Existing documents without metadata still searchable

---

## Future Enhancements (Out of Scope)

- Automatic metadata extraction from PDF content
- Batch metadata editing
- Metadata import from CSV/JSON
- Custom metadata fields per deployment

---

# Plan: PDF Archive with Download URLs

## Goal
When uploading a PDF, preserve the original file in an archive folder. Return a download URL in search results.

## Current State
- PDFs are uploaded via `/api/upload` endpoint in [main.py](backend/app/main.py)
- Files are saved to `./uploads/` with UUID prefix: `{uuid}_{original_filename}.pdf`
- The `file_path` is stored in `PDFDocument.file_path` column
- Search results return `content`, `page`, `relevance`, `pdf_id`, `filename` but no download URL

## Implementation Steps

### 1. Add Archive Folder Configuration
- Add `PDF_RAG_ARCHIVE_DIR` environment variable (default: `./archive`)
- Create the archive directory on startup in `main.py`

### 2. Copy PDF to Archive on Upload
- In the `/api/upload` endpoint, after saving to `./uploads/`:
  - Copy the original file to the archive folder using the original filename
  - If a file with the same name exists, add a numeric suffix (e.g., `document(1).pdf`)
- Add `archive_path` column to `PDFDocument` model to store the archive location

### 3. Add Download Endpoint
- Create `GET /api/archive/{filename}` endpoint to serve archived files
- Use `FileResponse` to stream the PDF with proper content-disposition headers

### 4. Include Download URL in Search Results
- Modify `_format_vector_search_results()` to include `download_url` field
- Format: `/api/archive/{encoded_filename}`
- Also update the MCP `/query` endpoint response

### 5. Database Migration
- Add `archive_path` column to `pdf_documents` table
- Update `_ensure_schema()` in `database.py` for legacy databases

## Files to Modify
1. [backend/app/database.py](backend/app/database.py) - Add `archive_path` column
2. [backend/app/main.py](backend/app/main.py) - Archive logic, download endpoint, search results

## Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `PDF_RAG_ARCHIVE_DIR` | `./archive` | Directory for archived original PDFs |
