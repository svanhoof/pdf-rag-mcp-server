"""Metadata Extraction Module.

This module extracts document metadata (authors, publication year, document type)
from PDF documents using an LLM (Anthropic Claude) via LangChain.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import fitz  # PyMuPDF

from app.database import DOCUMENT_TYPES

logger = logging.getLogger("metadata_extractor")


@dataclass
class DocumentMetadata:
    """Extracted metadata from a document."""

    authors: List[str]
    publication_year: Optional[int]
    document_type: Optional[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "authors": self.authors,
            "publication_year": self.publication_year,
            "document_type": self.document_type,
        }


def extract_text_from_first_pages(pdf_path: str, num_pages: int = 3) -> str:
    """Extract text from the first N pages of a PDF.

    Args:
        pdf_path: Path to the PDF file.
        num_pages: Number of pages to extract (default: 3).

    Returns:
        Combined text from the first N pages.
    """
    doc = fitz.open(pdf_path)
    texts = []

    pages_to_extract = min(num_pages, len(doc))
    for i in range(pages_to_extract):
        page = doc[i]
        text = page.get_text()
        if text.strip():
            texts.append(f"--- Page {i + 1} ---\n{text}")

    doc.close()
    return "\n\n".join(texts)


def extract_metadata_with_llm(text: str) -> DocumentMetadata:
    """Extract metadata from document text using an LLM.

    Args:
        text: Text content from the document's first pages.

    Returns:
        DocumentMetadata with extracted information.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    # Initialize the Anthropic LLM
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        anthropic_api_key=api_key,
        temperature=0,
        max_tokens=1024,
    )

    # Build the prompt
    document_types_str = ", ".join(DOCUMENT_TYPES)

    system_prompt = f"""You are a document metadata extraction assistant. Your task is to analyze
document text and extract the following information:

1. **Authors**: List of author names. Extract full names when available.
2. **Publication Year**: The year the document was published (4-digit year).
3. **Document Type**: Classify the document as one of: {document_types_str}

Respond in the following exact format (use these exact labels):
AUTHORS: <comma-separated list of authors, or "Unknown" if not found>
YEAR: <4-digit year, or "Unknown" if not found>
TYPE: <one of {document_types_str}, or "other" if unclear>

Be precise and only extract information that is clearly stated in the document.
For academic papers, look for author names near the title or in the header.
For the publication year, look for copyright notices, publication dates, or dates in headers/footers."""

    user_prompt = f"""Please extract metadata from the following document text:

{text}

Remember to respond with:
AUTHORS: <authors>
YEAR: <year>
TYPE: <type>"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    response_text = response.content

    return parse_llm_response(response_text)


def parse_llm_response(response_text: str) -> DocumentMetadata:
    """Parse the LLM response into a DocumentMetadata object.

    Args:
        response_text: Raw response text from the LLM.

    Returns:
        Parsed DocumentMetadata object.
    """
    authors: List[str] = []
    publication_year: Optional[int] = None
    document_type: Optional[str] = None

    lines = response_text.strip().split("\n")

    for line in lines:
        line = line.strip()

        if line.upper().startswith("AUTHORS:"):
            authors_str = line.split(":", 1)[1].strip()
            if authors_str.lower() != "unknown" and authors_str:
                # Split by comma and clean up each author name
                authors = [a.strip() for a in authors_str.split(",") if a.strip()]
                # Filter out any "Unknown" entries
                authors = [a for a in authors if a.lower() != "unknown"]

        elif line.upper().startswith("YEAR:"):
            year_str = line.split(":", 1)[1].strip()
            if year_str.lower() != "unknown" and year_str:
                try:
                    year = int(year_str)
                    if 1900 <= year <= 2100:
                        publication_year = year
                except ValueError:
                    pass

        elif line.upper().startswith("TYPE:"):
            type_str = line.split(":", 1)[1].strip().lower()
            if type_str in DOCUMENT_TYPES:
                document_type = type_str
            else:
                document_type = "other"

    return DocumentMetadata(
        authors=authors,
        publication_year=publication_year,
        document_type=document_type,
    )


def extract_metadata_from_pdf(pdf_path: str) -> DocumentMetadata:
    """Main function to extract metadata from a PDF file.

    This is the primary entry point for metadata extraction. It:
    1. Extracts text from the first 3 pages of the PDF
    2. Sends the text to an LLM for analysis
    3. Returns structured metadata

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        DocumentMetadata with authors, publication_year, and document_type.

    Raises:
        FileNotFoundError: If the PDF file doesn't exist.
        ValueError: If ANTHROPIC_API_KEY is not set.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Extracting metadata from: {pdf_path}")

    # Extract text from first 3 pages
    text = extract_text_from_first_pages(pdf_path, num_pages=3)

    if not text.strip():
        logger.warning(f"No text extracted from {pdf_path}")
        return DocumentMetadata(authors=[], publication_year=None, document_type="other")

    # Use LLM to extract metadata
    metadata = extract_metadata_with_llm(text)

    logger.info(f"Extracted metadata: authors={metadata.authors}, year={metadata.publication_year}, type={metadata.document_type}")

    return metadata
