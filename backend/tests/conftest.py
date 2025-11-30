"""Pytest configuration for isolated test environment.

Sets up separate databases for testing to avoid interfering with production data.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Create isolated test directories BEFORE importing anything from the app
_test_temp_dir = tempfile.mkdtemp(prefix="pdf_rag_test_")
_test_data_dir = Path(_test_temp_dir) / "data"
_test_data_dir.mkdir(parents=True, exist_ok=True)

# Set environment variables for test isolation
os.environ["PDF_RAG_LANCE_DB"] = str(_test_data_dir / "lance_db")
os.environ["PDF_RAG_CHROMA_DB"] = str(_test_data_dir / "chroma_db")
os.environ["PDF_RAG_DB_PATH"] = str(_test_data_dir / "test_knowledge_base.db")

# Create static directories required by the app
backend_dir = Path(__file__).parent.parent
static_dir = backend_dir / "static" / "static"
static_dir.mkdir(parents=True, exist_ok=True)


def pytest_configure(config):
    """Called after command line options have been parsed and all plugins loaded."""
    print(f"\n[TEST] Using isolated test directory: {_test_temp_dir}")
    print(f"[TEST] Lance DB: {os.environ['PDF_RAG_LANCE_DB']}")
    print(f"[TEST] SQLite DB: {os.environ['PDF_RAG_DB_PATH']}")


def pytest_unconfigure(config):
    """Called before test process exits."""
    # Clean up test directory
    if Path(_test_temp_dir).exists():
        try:
            shutil.rmtree(_test_temp_dir)
            print(f"\n[TEST] Cleaned up test directory: {_test_temp_dir}")
        except Exception as e:
            print(f"\n[TEST] Failed to clean up test directory: {e}")
