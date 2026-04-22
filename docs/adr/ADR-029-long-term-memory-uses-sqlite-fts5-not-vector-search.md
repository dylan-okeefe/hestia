# ADR-029: Long-term memory uses SQLite FTS5, not vector search

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** The agent needs persistent, searchable notes that survive across
  sessions. The two main approaches are vector search (embedding-based
  similarity) and full-text search (keyword/phrase matching).

- **Decision:**
  1. Use SQLite FTS5 virtual tables for memory search. The table stores
     content, tags, session_id, and created_at. Search uses BM25 ranking.
  2. MemoryStore handles its own DDL because SQLAlchemy doesn't support
     FTS5 virtual tables through metadata.create_all().
  3. Memory tools (search_memory, save_memory, list_memories) use the
     factory pattern (make_*_tool) to bind to a MemoryStore instance,
     same as read_artifact.
  4. No vector DB, no embeddings, no external services. FTS5 is built
     into SQLite and requires zero additional dependencies.

- **Consequences:**
  - FTS5 search is keyword-based, not semantic. "car" won't find
    memories about "automobile". This is acceptable for a personal
    assistant where the user's own vocabulary is consistent.
  - FTS5 is extremely fast (sub-millisecond for typical query volumes).
    No GPU memory consumed, no embedding model loaded.
  - Vector search can be added later as a plugin (e.g., sqlite-vec)
    without changing the MemoryStore interface. The search() method
    signature stays the same.
  - The FTS5 table lives in the same SQLite database as everything
    else. A separate memory database (as originally designed) adds
    complexity with no current benefit.
