-- SQLite schema for search cache
-- Version 1.0

-- Version tracking for schema migrations
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Main documents table (mirrors YAML structure)
CREATE TABLE IF NOT EXISTS documents (
    uri TEXT PRIMARY KEY,
    name TEXT,
    url TEXT NOT NULL,
    summary TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    tags TEXT,  -- JSON array as string
    extra TEXT,  -- JSON object as string
    created_at TIMESTAMP,
    modified_at TIMESTAMP
);

-- FTS5 virtual table for full-text search
-- Using porter stemming and unicode61 tokenizer for better matching
-- Note: FTS5 table maintains its own content (not content-less)
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    uri UNINDEXED,
    name,
    summary,
    tags,
    extra_text,  -- Flattened extra fields
    tokenize='porter unicode61'
);

-- Index for fast URI lookups
CREATE INDEX IF NOT EXISTS idx_documents_uri ON documents(uri);

-- Metadata table to track YAML sync state
CREATE TABLE IF NOT EXISTS sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- BM25 ranking tables

-- Term statistics for BM25 IDF calculation
CREATE TABLE IF NOT EXISTS term_stats (
    term TEXT PRIMARY KEY,
    doc_frequency INTEGER,  -- Number of docs containing term
    collection_frequency INTEGER  -- Total occurrences across all docs
);

-- Document statistics for BM25 normalization
CREATE TABLE IF NOT EXISTS document_stats (
    uri TEXT PRIMARY KEY,
    length_name INTEGER,
    length_summary INTEGER,
    length_tags INTEGER,
    length_extra INTEGER,
    length_total INTEGER,
    FOREIGN KEY (uri) REFERENCES documents(uri)
);

-- Collection-level statistics
CREATE TABLE IF NOT EXISTS collection_stats (
    key TEXT PRIMARY KEY,
    value REAL
);
-- Stores: avg_doc_length, total_docs

-- Precomputed term vectors for documents
CREATE TABLE IF NOT EXISTS document_terms (
    uri TEXT,
    field TEXT,  -- 'name', 'summary', 'tags', 'extra'
    term TEXT,
    frequency INTEGER,
    PRIMARY KEY (uri, field, term),
    FOREIGN KEY (uri) REFERENCES documents(uri)
);

CREATE INDEX IF NOT EXISTS idx_document_terms_term ON document_terms(term);
CREATE INDEX IF NOT EXISTS idx_document_terms_uri ON document_terms(uri);

-- Semantic search tables

-- Embeddings table for vector similarity search
CREATE TABLE IF NOT EXISTS embeddings (
    uri TEXT PRIMARY KEY,
    embedding BLOB,  -- Serialized numpy array (float32)
    model_version TEXT,  -- Track which model generated it
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (uri) REFERENCES documents(uri)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_version);

-- Configuration for embedding model
CREATE TABLE IF NOT EXISTS embedding_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Stores: model_name, dimension, distance_metric

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
