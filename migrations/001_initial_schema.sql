-- Initial schema for document store
-- This migration creates the documents table and necessary indexes

-- Enable pg_trgm extension for trigram text search (optional, requires superuser)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT,
    name TEXT,
    mime_type TEXT NOT NULL,
    tags JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW(),
    extra JSONB,
    size INTEGER NOT NULL DEFAULT 0,
    content BYTEA NOT NULL
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_documents_created_at
ON documents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_name
ON documents(name);

CREATE INDEX IF NOT EXISTS idx_documents_uuid
ON documents(uuid);

-- Full-text search index on name (only if pg_trgm is available)
CREATE INDEX IF NOT EXISTS idx_documents_name_trgm
ON documents USING gin(name gin_trgm_ops);
