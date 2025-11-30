"""LanceDB vector database backend."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

import lancedb
import numpy as np
import pyarrow as pa
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from app.database import PDFDocument, PDFMarkdownPage, SessionLocal
from .base import BaseVectorBackend, markdown_is_current

logger = logging.getLogger("vector_store.lance")


class LanceVectorBackend(BaseVectorBackend):
    """Vector backend backed by LanceDB tables."""
    @staticmethod
    def _load_sentence_transformer(device_preference: str) -> SentenceTransformer:
        """Load SentenceTransformer while handling GPU fallbacks and meta tensor issues."""
        try:
            return SentenceTransformer("all-MiniLM-L6-v2", device=device_preference)
        except NotImplementedError as exc:
            logger.warning(
                "SentenceTransformer failed on device '%s' due to meta tensors: %s; falling back to default init",
                device_preference,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            if device_preference.lower() != "cpu":
                logger.warning(
                    "SentenceTransformer failed on device '%s': %s; retrying on CPU",
                    device_preference,
                    exc,
                )
            else:
                raise

        # Final fallback path: initialise without explicit device, then move to CPU explicitly.
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model
        except Exception as final_exc:  # noqa: BLE001
            logger.error("SentenceTransformer initialization failed on all attempts: %s", final_exc)
            raise

    _TABLE_NAME = "pdf_documents"

    # Explicit PyArrow schema to avoid null-type inference issues
    # The vector dimension is 384 for all-MiniLM-L6-v2
    _TABLE_SCHEMA = pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), 384)),
        pa.field("pdf_id", pa.int64()),
        pa.field("source", pa.string()),
        pa.field("chunk_id", pa.string()),
        pa.field("page", pa.int64()),
        pa.field("batch", pa.string()),
        pa.field("index", pa.int64()),
        pa.field("length", pa.int64()),
        pa.field("timestamp", pa.float64()),
        pa.field("metadata", pa.string()),  # JSON serialized
        # Document-level metadata for filtered search
        pa.field("publication_year", pa.int64()),
        pa.field("authors", pa.list_(pa.string())),
        pa.field("document_type", pa.string()),
    ])

    def __init__(self, persist_directory: Optional[str] = None):
        if persist_directory is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.dirname(current_dir)
            persist_directory = os.path.join(backend_dir, "lance_db")

        persist_directory = os.path.abspath(persist_directory)
        super().__init__(persist_directory=persist_directory)

        os.makedirs(persist_directory, exist_ok=True)
        logger.info("Initializing LanceDB backend in %s", persist_directory)
        self.client = lancedb.connect(persist_directory)
        self.table = self._open_table()

        if self.table is None:
            logger.info("Lance table not found; will be created on first insert")
            self.ensure_async_rebuild()
        elif self.get_document_count() == 0:
            logger.info("Lance table empty; scheduling rebuild from markdown")
            self.ensure_async_rebuild()

    def _open_table(self):
        try:
            if self._TABLE_NAME in self.client.table_names():
                return self.client.open_table(self._TABLE_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to open Lance table: %s", exc)
        return None

    def _ensure_table(self, records: List[Dict[str, Any]]) -> None:
        if self.table is not None:
            return
        if not records:
            return
        existing = self._open_table()
        if existing is not None:
            self.table = existing
            return

        try:
            # Create table with explicit schema to ensure proper types
            self.table = self.client.create_table(
                self._TABLE_NAME,
                records,
                schema=self._TABLE_SCHEMA,
            )
            logger.info("Created Lance table with %s initial rows", len(records))
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "already exists" in message.lower():
                logger.info("Lance table already existed; opening existing table")
                self.table = self._open_table()
                if self.table is not None:
                    return
            logger.error("Unable to create Lance table: %s", exc)
            raise

    def _build_records(
        self,
        chunks: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        metadatas = metadatas or [{} for _ in chunks]
        for chunk, embedding, meta in zip(chunks, embeddings, metadatas):
            # Use sentinel values for metadata fields to ensure proper type inference
            # 0 means "unset" for publication_year, "" means "unset" for document_type
            publication_year = meta.get("publication_year")
            document_type = meta.get("document_type")
            authors = meta.get("authors")

            record = {
                "id": f"doc_{meta.get('pdf_id')}_{meta.get('chunk_id')}",
                "text": chunk,
                "vector": embedding.tolist(),
                "pdf_id": int(meta.get("pdf_id") or 0),
                "source": str(meta.get("source") or ""),
                "chunk_id": str(meta.get("chunk_id") or ""),
                "page": int(meta.get("page") or 0),
                "batch": str(meta.get("batch") or ""),
                "index": int(meta.get("index") or 0),
                "length": int(meta.get("length") or 0),
                "timestamp": float(meta.get("timestamp") or 0.0),
                "metadata": json.dumps(meta),  # Serialize as JSON string
                # Document-level metadata for filtered search
                # Use sentinel values (0, "", []) to ensure proper type inference in LanceDB
                "publication_year": int(publication_year) if publication_year else 0,
                "authors": list(authors) if authors else [],
                "document_type": str(document_type) if document_type else "",
            }
            records.append(record)
        return records

    def add_documents(
        self,
        chunks: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        if not chunks:
            return True
        try:
            records = self._build_records(chunks, embeddings, metadatas)
            if self.table is None:
                self._ensure_table(records)
                if self.table is None:
                    logger.error("Lance table could not be initialized for add_documents call")
                    return False
            self.table.add(records)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Error adding documents to LanceDB: %s", exc, exc_info=True)
            return False

    def search(
        self,
        query_embedding: np.ndarray,
        n_results: int = 5,
        filter_criteria: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        # Try to open table if it was created after init
        if self.table is None:
            self.table = self._open_table()
        if self.table is None or self.get_document_count() == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        try:
            requested = max(int(n_results or 0), 0)
            offset_val = max(int(offset or 0), 0)
            fetch_total = requested + offset_val + 1
            if fetch_total <= 0:
                fetch_total = 1

            query = self.table.search(query_embedding.tolist())
            if filter_criteria:
                query = query.where(filter_criteria)
            df = query.limit(fetch_total).to_pandas()

            if df.empty:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            documents = df["text"].tolist()
            # Deserialize metadata from JSON strings
            raw_metadatas = df["metadata"].tolist()
            metadatas = []
            for raw in raw_metadatas:
                if isinstance(raw, str):
                    try:
                        metadatas.append(json.loads(raw))
                    except json.JSONDecodeError:
                        metadatas.append({})
                elif isinstance(raw, dict):
                    metadatas.append(raw)
                else:
                    metadatas.append({})

            scores_series = df["score"] if "score" in df.columns else None
            distance_series = df["distance"] if "distance" in df.columns else None

            if scores_series is not None:
                scores_all = [float(max(0.0, min(1.0, value))) for value in scores_series.tolist()]
            elif distance_series is not None:
                distance_values = [float(value) for value in distance_series.tolist()]
                scores_all = [max(0.0, min(1.0, 1.0 - value)) for value in distance_values]
            else:
                scores_all = [0.0 for _ in documents]

            if distance_series is not None:
                distances_all = [max(0.0, float(value)) for value in distance_series.tolist()]
            else:
                distances_all = [max(0.0, 1.0 - score) for score in scores_all]

            window_docs = documents[offset_val : offset_val + requested] if requested > 0 else []
            window_meta = metadatas[offset_val : offset_val + requested] if requested > 0 else []
            window_dist = distances_all[offset_val : offset_val + requested] if requested > 0 else []
            window_scores = scores_all[offset_val : offset_val + requested] if requested > 0 else []
            has_more = len(documents) > offset_val + requested

            return {
                "documents": [window_docs],
                "metadatas": [window_meta],
                "distances": [window_dist],
                "scores": [window_scores],
                "has_more": has_more,
                "offset": offset_val,
                "limit": requested,
                "total_fetched": len(documents),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Error querying LanceDB: %s", exc, exc_info=True)
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def get_document_count(self) -> int:
        if self.table is None:
            return 0
        try:
            return self.table.count_rows()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to count Lance rows: %s", exc)
            return 0

    def reset(self) -> bool:
        try:
            if self._TABLE_NAME in self.client.table_names():
                self.client.drop_table(self._TABLE_NAME)
            self.table = None
            self.ensure_async_rebuild()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to reset Lance table: %s", exc)
            return False

    def _delete_where_expr(self, filter: Dict[str, Any]) -> Optional[str]:
        if not filter:
            return None
        clauses = []
        for key, value in filter.items():
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                clauses.append(f"{key} == '{escaped}'")
            else:
                clauses.append(f"{key} == {value}")
        return " and ".join(clauses) if clauses else None

    def delete(
        self,
        filter: Optional[Dict[str, Any]] = None,
        ids: Optional[Iterable[str]] = None,
    ) -> bool:
        if self.table is None:
            return True
        try:
            if filter:
                expr = self._delete_where_expr(filter)
                if expr:
                    self.table.delete(where=expr)
                return True
            if ids:
                id_list = list(ids)
                if not id_list:
                    return True
                quoted_items = []
                for item in id_list:
                    safe_item = str(item).replace("'", "''")
                    quoted_items.append(f"'{safe_item}'")
                quoted = ",".join(quoted_items)
                self.table.delete(where=f"id in ({quoted})")
                return True
            logger.warning("Lance delete called without filter or ids")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Error deleting from LanceDB: %s", exc, exc_info=True)
            return False

    def update_document_metadata(
        self,
        pdf_id: int,
        publication_year: Optional[int] = None,
        authors: Optional[List[str]] = None,
        document_type: Optional[str] = None,
    ) -> bool:
        """Update metadata fields on all chunks belonging to a document.

        LanceDB doesn't support in-place updates, so we:
        1. Read all chunks for the document
        2. Update metadata fields
        3. Delete old chunks
        4. Re-add with updated metadata
        """
        # Try to open table if it was created after init
        if self.table is None:
            self.table = self._open_table()
        if self.table is None:
            logger.warning("Cannot update metadata: Lance table not initialized")
            return False

        try:
            # Fetch all chunks for this pdf_id
            where_expr = f"pdf_id == {pdf_id}"
            df = self.table.search().where(where_expr).limit(100000).to_pandas()

            if df.empty:
                logger.info("No chunks found for pdf_id=%s, nothing to update", pdf_id)
                return True

            logger.info("Updating metadata for %d chunks (pdf_id=%s)", len(df), pdf_id)

            # Build updated records with proper types matching the schema
            updated_records = []
            for _, row in df.iterrows():
                # Preserve existing metadata (it's stored as JSON string)
                existing_meta = row.get("metadata", "{}")
                if isinstance(existing_meta, str):
                    existing_meta = existing_meta  # Already a string
                else:
                    existing_meta = json.dumps(existing_meta) if existing_meta else "{}"

                record = {
                    "id": str(row["id"]),
                    "text": str(row["text"]),
                    "vector": list(row["vector"]),
                    "pdf_id": int(row["pdf_id"]),
                    "source": str(row.get("source") or ""),
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "page": int(row.get("page") or 0),
                    "batch": str(row.get("batch") or ""),
                    "index": int(row.get("index") or 0),
                    "length": int(row.get("length") or 0),
                    "timestamp": float(row.get("timestamp") or 0.0),
                    "metadata": existing_meta,
                    # Updated metadata fields - use sentinel values for unset
                    "publication_year": int(publication_year) if publication_year is not None else 0,
                    "authors": list(authors) if authors is not None else [],
                    "document_type": str(document_type) if document_type is not None else "",
                }
                updated_records.append(record)

            # Delete old chunks
            self.table.delete(where=where_expr)

            # Re-add with updated metadata
            self.table.add(updated_records)
            logger.info("Successfully updated metadata for pdf_id=%s", pdf_id)
            return True

        except Exception as exc:  # noqa: BLE001
            logger.error("Error updating metadata in LanceDB: %s", exc, exc_info=True)
            return False

    def rebuild_from_markdown(self) -> None:
        if self.get_document_count() > 0:
            logger.info("Lance store already populated; skipping rebuild")
            return

        db = SessionLocal()
        try:
            processed_docs = (
                db.query(PDFDocument)
                .filter(PDFDocument.processed == True)  # noqa: E712
                .order_by(PDFDocument.id)
                .all()
            )
            if not processed_docs:
                return

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )

            requested_device = os.getenv("SENTENCE_TRANSFORMERS_DEVICE", "cpu")
            logger.info("Rebuilding Lance embeddings on %s", requested_device)
            model = self._load_sentence_transformer(requested_device)

            rebuilt_any = False
            for doc in processed_docs:
                if doc.blacklisted:
                    continue
                if not markdown_is_current(doc):
                    continue

                pages = (
                    db.query(PDFMarkdownPage)
                    .filter(PDFMarkdownPage.pdf_id == doc.id)
                    .order_by(PDFMarkdownPage.page)
                    .all()
                )
                if not pages:
                    continue

                doc_chunks: List[str] = []
                metadatas: List[Dict[str, Any]] = []
                batch_id = f"rebuild-{uuid.uuid4().hex[:8]}"
                chunk_counter = 0

                for page in pages:
                    page_text = (page.markdown or "").strip()
                    if not page_text:
                        continue
                    page_chunks = text_splitter.split_text(page_text)
                    for chunk in page_chunks:
                        doc_chunks.append(chunk)
                        metadatas.append(
                            {
                                "source": doc.filename,
                                "chunk_id": f"{batch_id}_{chunk_counter}",
                                "pdf_id": doc.id,
                                "page": page.page,
                                "batch": batch_id,
                                "index": chunk_counter,
                                "length": len(chunk),
                                "timestamp": time.time(),
                                # Document metadata from DB, using sentinel values for unset
                                "publication_year": doc.publication_year or 0,
                                "authors": doc.authors or [],
                                "document_type": doc.document_type or "",
                            }
                        )
                        chunk_counter += 1

                if not doc_chunks:
                    continue

                embeddings = model.encode(doc_chunks)
                if self.add_documents(doc_chunks, embeddings, metadatas):
                    rebuilt_any = True

            if rebuilt_any:
                logger.info("Lance rebuild finished")
        finally:
            db.close()
