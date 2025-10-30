-- Add users table and owner_id to documents
-- This migration creates the users table with id and uuid columns
-- and adds an owner_id foreign key to the documents table

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create unique index on uuid
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uuid
ON users(uuid);

-- Add owner_id column to documents table
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS owner_id BIGINT;

-- Create index on owner_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_documents_owner_id
ON documents(owner_id);

ALTER TABLE documents
ADD CONSTRAINT fk_documents_owner_id
FOREIGN KEY (owner_id) REFERENCES users(id)
ON DELETE SET NULL;
