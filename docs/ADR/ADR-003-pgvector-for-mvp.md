# ADR-003: pgvector for MVP

- Status: Accepted
- Date: 2026-09-15

The MVP uses PostgreSQL with pgvector for document chunks and memory embeddings. A VectorStore abstraction keeps future migration to a dedicated vector database possible without coupling the runtime to one vendor.

