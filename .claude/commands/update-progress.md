---
description: Update the Progress.md file with current implementation status
---

You are updating the progress report at `instructions/Progress.md`. Follow these guidelines:

## Format Requirements

The progress report must be **concise** - a checklist of implemented/not-implemented features, NOT a detailed changelog.

See `instructions/Roadmap.md` for the list of planned features.

## Structure

```markdown
# Progress Report

Last Updated: [DATE]

## Phase 1: Core Infrastructure
- [x] Feature 1 - Brief description
- [x] Feature 2 - Brief description
- [ ] Feature 3 - Not yet implemented

## Phase 2: Enhanced Features
- [ ] Feature 1 - Brief description
- [ ] Feature 2 - Brief description

## Current Status
Brief 1-2 sentence summary of where the project stands.

## Next Steps
- Priority item 1
- Priority item 2
- Priority item 3
```

## Guidelines

1. **Concise Over Detailed**: Each feature gets ONE line with a checkbox
2. **No Changelogs**: Don't track when things changed or who changed them
3. **Status Focus**: What IS done vs what ISN'T done
4. **Brief Descriptions**: 5-10 words max per feature
5. **Group by Phase**: Organize features by development phase
6. **No Code Snippets**: Don't include file paths, line numbers, or code
7. **No Technical Debt Section**: Keep focus on features, not implementation details
8. **No Dependency Lists**: Don't list every package installed
9. **Current Status**: 1-2 sentences summarizing overall progress
10. **Next Steps**: 3-5 bullet points of upcoming priorities

## What to Include

- High-level features (e.g., "PostgreSQL storage backend", "REST API endpoints")
- Major capabilities (e.g., "Document search", "File upload validation")
- Deployment status (e.g., "Docker deployment", "Health checks")
- Testing status (e.g., "Integration tests", "PostgreSQL tests")

## What to Exclude

- File paths and line numbers
- Detailed implementation notes
- Technical debt items
- Code examples
- Commit hashes
- Version numbers of dependencies
- Detailed error messages
- Step-by-step instructions

## Example of Good Format

```markdown
## Phase 1: Core Infrastructure ✅
- [x] MCP server with stdio and HTTP transports
- [x] PostgreSQL storage backend with connection pooling
- [x] Filesystem storage backend
- [x] Document upload with size validation
- [x] Full-text search
- [x] REST API endpoints
- [x] Docker deployment
- [x] Integration tests for all backends
- [ ] Authentication and authorization

## Current Status
Phase 1 complete. All core features implemented and tested. Ready for Phase 2.

## Next Steps
- Implement document parsing (PDF, DOCX)
- Add vector embeddings for semantic search
- Create admin UI
```

## Example of Bad Format (Too Verbose)

```markdown
## Phase 1: Core Infrastructure
### 1. MCP Server Implementation
- **Status:** ✅ Complete
- **Details:**
  - FastMCP-based server (`fastmcp~=2.12`)
  - Support for both stdio and HTTP/SSE transports
  - Environment-based storage backend selection

**Files:**
- `src/asta_resource_repository/server.py:1-136`
```

## Your Task

Read the current `instructions/Progress.md` file and rewrite it following the concise format above. Focus on WHAT is done, not HOW it was done or WHEN it was done.
