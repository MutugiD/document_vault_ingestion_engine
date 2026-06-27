"""Local Matter RAG Connector package."""

from rag.core import (
    RAG_SCHEMA_VERSION,
    Citation,
    ContextChunk,
    RagAnswerPacket,
    RagError,
    RagRetrievalResult,
    answer_confidence,
    build_answer_packet,
    build_rag_index,
    chunk_text,
    initialize_rag_store,
    retrieve_context,
)

__all__ = [
    "RAG_SCHEMA_VERSION",
    "Citation",
    "ContextChunk",
    "RagAnswerPacket",
    "RagError",
    "RagRetrievalResult",
    "answer_confidence",
    "build_answer_packet",
    "build_rag_index",
    "chunk_text",
    "initialize_rag_store",
    "retrieve_context",
]
