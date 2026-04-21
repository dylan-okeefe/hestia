# ADR-0006: Search is FTS-only at first

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Long-term memory needs search. Vector DBs (Chroma, Weaviate, pgvector)
  add deployment complexity and GPU memory pressure. For a personal assistant,
  full-text search is often sufficient.
- **Decision:** SQLite FTS5 is the only search in v1. If vector search is needed
  later, add it as a plugin (e.g., via `sqlite-vec` or separate table) without
  breaking the FTS schema.
- **Consequences:** Semantic similarity queries are not supported in v1. Users
  must use keyword-based memory search.
