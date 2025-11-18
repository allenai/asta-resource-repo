-- Initial schema for document store
-- This migration creates the documents and users tables with all necessary indexes

-- Enable pg_trgm extension for trigram text search (optional, requires superuser)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT,
    name TEXT,
    mime_type TEXT NOT NULL,
    tags JSONB,
    extra JSONB,
    size INTEGER NOT NULL DEFAULT 0,
    binary_content BYTEA,
    text_content TEXT,
    owner_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create unique index on users.uuid
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uuid
ON users(uuid);

-- Create indexes for common queries on documents
CREATE INDEX IF NOT EXISTS idx_documents_created_at
ON documents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_name
ON documents(name);

CREATE INDEX IF NOT EXISTS idx_documents_uuid
ON documents(uuid);

CREATE INDEX IF NOT EXISTS idx_documents_owner_id
ON documents(owner_id);

-- Create composite index on documents (uuid) for faster URI lookups
CREATE INDEX IF NOT EXISTS idx_documents_uuid
ON documents(uuid);

-- Full-text search index on name (only if pg_trgm is available)
CREATE INDEX IF NOT EXISTS idx_documents_name_trgm
ON documents USING gin(name gin_trgm_ops);

-- Add foreign key constraint from documents to users
ALTER TABLE documents
ADD CONSTRAINT fk_documents_owner_id
FOREIGN KEY (owner_id) REFERENCES users(id)
ON DELETE SET NULL;
