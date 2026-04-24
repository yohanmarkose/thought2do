"""Vector service: optional Pinecone integration.

Implements `VectorService` for embedding-based task dedup and the
future vault feature. When `PINECONE_API_KEY` is unset the service
is inert — every method is a silent no-op, guarded by `is_enabled()`.
"""
