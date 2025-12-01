import axios from 'axios';

export const fetchDocumentMarkdown = async ({ id, start_page = 1, max_pages = null, max_characters = null, title = null }) => {
  if (id) {
    const params = { start_page };
    if (max_pages) params.max_pages = max_pages;
    if (max_characters) params.max_characters = max_characters;
    const response = await axios.get(`/api/documents/${id}/markdown`, { params });
    return response.data;
  }

  // Fallback to title-based MCP endpoint (backwards compatibility)
  const response = await axios.get(`/mcp/documents/markdown`, {
    params: { title, start_page, max_pages, max_characters }
  });
  return response.data;
};

export const searchDocuments = async ({
  query,
  limit = 10,
  offset = 0,
  publication_year = null,
  document_type = null,
  document_types = null,
  author = null,
  year_start = null,
  year_end = null,
}) => {
  const params = { q: query, limit, offset };
  // Year range takes precedence over exact year
  if (year_start || year_end) {
    if (year_start) params.year_start = year_start;
    if (year_end) params.year_end = year_end;
  } else if (publication_year) {
    params.publication_year = publication_year;
  }
  // Multiple document types takes precedence over single type
  if (document_types && document_types.length > 0) {
    params.document_types = document_types.join(',');
  } else if (document_type) {
    params.document_type = document_type;
  }
  if (author) params.author = author;
  const response = await axios.get('/api/search', { params });
  return response.data;
};

export const updateDocumentMetadata = async ({ id, title, publication_year, authors, document_type }) => {
  const payload = {};
  if (title !== undefined) payload.title = title;
  if (publication_year !== undefined) payload.publication_year = publication_year;
  if (authors !== undefined) payload.authors = authors;
  if (document_type !== undefined) payload.document_type = document_type;
  const response = await axios.patch(`/api/documents/${id}/metadata`, payload);
  return response.data;
};

// Valid document types (keep in sync with backend)
export const DOCUMENT_TYPES = ['paper', 'handbook', 'manual', 'report', 'other'];
