# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PDF RAG MCP Server is a document knowledge base system that processes PDFs, stores embeddings in a vector database, and exposes semantic search via both a web UI and the Model Context Protocol (MCP) for integration with AI tools like Cursor.

## Common Commands

### Quick Start
```bash
# Install dependencies (Python 3.12+ required)
uv pip install -r backend/requirements.txt

# Start the full application (requires pre-built frontend in backend/static/)
uv run run.py
```

### Backend Development
```bash
cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Development
```bash
cd frontend
npm install
npm run dev          # Dev server with hot reload, proxies to backend
npm run build        # Production build
npm run lint         # ESLint
```

### Building Frontend for Production
```bash
./build_frontend.py  # Builds and copies to backend/static/
```

### Docker
```bash
docker build -t pdf-rag-mcp-server:local .
PDF_RAG_IMAGE=pdf-rag-mcp-server:local docker compose up -d
```

### Testing
```bash
# Run all unit tests (must run from backend directory)
cd backend && uv run pytest tests/ -v

# Run specific test files
cd backend && uv run pytest tests/test_baseline.py -v
cd backend && uv run pytest tests/test_metadata.py -v

# Manual testing utilities
python3 backend/tests/test_query.py --query "search term"  # Test vector search
python3 backend/tests/test_query.py --list                 # List documents
python3 backend/tests/test_query.py --reset                # Reset vector store
```

**Note:** Tests require a sample PDF at `input/paper.pdf`. Tests use isolated temporary directories for databases to avoid affecting development data.

### Syntax Validation
```bash
python3 -m compileall backend/app/  # Check Python syntax
docker compose config               # Validate compose YAML
```

## Architecture

### Backend (`backend/app/`)
- **main.py**: FastAPI app hosting REST API, WebSocket broadcasting, and MCP sub-app mounted at `/mcp/v1`
- **pdf_processor.py**: PDF extraction using PyMuPDF, chunking via LangChain's RecursiveCharacterTextSplitter (1000 chars, 200 overlap), embedding with `all-MiniLM-L6-v2`
- **vector_store.py**: Facade over pluggable vector backends (LanceDB default, Chroma optional via `PDF_RAG_VECTOR_BACKEND`)
- **pdf_watcher.py**: Directory watcher for auto-ingesting PDFs from `PDF_RAG_WATCH_DIR`
- **database.py**: SQLAlchemy models with SQLite at `backend/pdf_knowledge_base.db`
- **websocket.py**: Real-time status updates via `{type, filename, status}` payloads

### Frontend (`frontend/src/`)
- React 19 + Chakra UI + Vite
- WebSocket connection to `ws://{host}:8000/ws` for live processing updates
- API calls use Axios with relative paths (`/api/*`)
- Production builds go to `backend/static/` (Vite `base: '/static/'`)

### Key Data Flows
1. **Upload**: File → `/api/upload` → DB row → background `_process_pdf_background` → chunks → vector store
2. **Auto-ingest**: Watcher scans `PDF_RAG_WATCH_DIR` → compares mtime → processes new/changed PDFs
3. **Search**: Query → embed with same model → vector similarity search → return chunks with metadata

### Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_PORT` | 8000 | Backend HTTP port |
| `MCP_PORT` | 7800 | MCP endpoint port |
| `PDF_RAG_VECTOR_BACKEND` | lance | Vector store: `lance` or `chroma` |
| `PDF_RAG_WATCH_DIR` | /app/auto_ingest | Directory watcher path |
| `SENTENCE_TRANSFORMERS_DEVICE` | cpu | Set to `cuda` for GPU embeddings |

## Development Guidelines

- Use Conventional Commits (`feat`, `fix`, `chore`) for semantic-release versioning
- Feature branches preferred over direct commits to `master`
- Keep `VITE_APP_VERSION` synced with releases (propagated via Docker build arg `APP_VERSION`)
- Chunk metadata keys (`pdf_id`, `chunk_id`, `page`, `batch`) must remain stable for downstream compatibility
- WebSocket events follow `{type, ...}` envelope pattern
