# Asta Resource Repository

An MCP/REST server for storing and sharing resources created by Asta users/agents.

An Asta Resource:
 - Is identified by an `asta://` URL
 - Is mutable
 - Is owned by an individual user, who grants access to other users
 - Can be accessed by both Ai2 and non-Ai2 applications
 - Can be uploaded by a user or an agent
   - Stored in the repository
   - Optionally shared with other users
   - Editable by agents and users
 - Can be a pointer to an externally-managed resource
   - e.g. a public URL
   - or a local file reference
   - User provides metadata
 - Is searchable
   - Automatic summary is indexed for keyword/semantic search
   - Metadata-based filtering
   - Searches only documents that the user has access to

Goals:
  - Long-lived content for user-level or project-level context
  - Source of truth for artifacts shared between agents
  - Interoperability with third-party tools
