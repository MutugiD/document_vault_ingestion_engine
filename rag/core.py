"""Local, citation-first RAG retrieval over matter document versions."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

RAG_SCHEMA_VERSION = "1"
VECTOR_DIMENSIONS = 64
DEFAULT_CHUNK_WORDS = 90
DEFAULT_CHUNK_OVERLAP = 20


class RagError(Exception):
    """Base RAG failure."""


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    matter_id: str
    document_id: str
    version_id: str
    title: str
    document_type: str
    lifecycle_status: str
    chunk_index: int
    text: str


@dataclass(frozen=True)
class Citation:
    citation_id: str
    matter_id: str
    document_id: str
    version_id: str
    title: str
    chunk_index: int


@dataclass(frozen=True)
class RagRetrievalResult:
    chunk: ContextChunk
    citation: Citation
    sparse_score: float
    vector_score: float
    rerank_score: float


@dataclass(frozen=True)
class RagAnswerPacket:
    question: str
    grounded_context: str
    citations: tuple[Citation, ...]
    retrieval_results: tuple[RagRetrievalResult, ...]
    safety_notice: str


def initialize_rag_store(vault_root: Path) -> None:
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)


def build_rag_index(vault_root: Path, *, matter_id: str | None = None) -> int:
    """Build local RAG chunks from extracted document-version text."""

    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        if matter_id is None:
            connection.execute("DELETE FROM rag_chunks")
        else:
            connection.execute("DELETE FROM rag_chunks WHERE matter_id = ?", (matter_id,))

        rows = _document_version_rows(connection, matter_id=matter_id)
        indexed_count = 0
        for row in rows:
            for index, chunk in enumerate(chunk_text(str(row["extracted_text"]))):
                chunk_id = _chunk_id(str(row["version_id"]), index, chunk)
                vector = _hashed_vector(chunk)
                connection.execute(
                    """
                    INSERT INTO rag_chunks (
                        chunk_id, matter_id, document_id, version_id, title,
                        document_type, lifecycle_status, chunk_index, text, vector_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        str(row["matter_id"]),
                        str(row["document_id"]),
                        str(row["version_id"]),
                        str(row["title"]),
                        str(row["document_type"]),
                        str(row["lifecycle_status"]),
                        index,
                        chunk,
                        json.dumps(vector, separators=(",", ":")),
                    ),
                )
                indexed_count += 1
    return indexed_count


def retrieve_context(
    vault_root: Path,
    query: str,
    *,
    matter_id: str | None = None,
    top_k: int = 5,
) -> tuple[RagRetrievalResult, ...]:
    """Retrieve and rerank local context chunks with citations."""

    query_terms = _tokenize(query)
    query_vector = _hashed_vector(query)
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        rows = _candidate_rows(connection, matter_id=matter_id)

    scored: list[RagRetrievalResult] = []
    for row in rows:
        chunk = _row_to_chunk(row)
        sparse_score = _sparse_score(query_terms, chunk.text)
        vector_score = _cosine_similarity(query_vector, json.loads(str(row["vector_json"])))
        if sparse_score == 0 and vector_score == 0:
            continue
        lifecycle_boost = 0.04 if chunk.lifecycle_status in {"filed", "served"} else 0.0
        rerank_score = (0.55 * sparse_score) + (0.40 * vector_score) + lifecycle_boost
        scored.append(
            RagRetrievalResult(
                chunk=chunk,
                citation=Citation(
                    citation_id=f"C{len(scored) + 1}",
                    matter_id=chunk.matter_id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    title=chunk.title,
                    chunk_index=chunk.chunk_index,
                ),
                sparse_score=sparse_score,
                vector_score=vector_score,
                rerank_score=rerank_score,
            )
        )

    ordered = sorted(scored, key=lambda result: result.rerank_score, reverse=True)[:top_k]
    return tuple(
        RagRetrievalResult(
            chunk=result.chunk,
            citation=Citation(
                citation_id=f"C{index + 1}",
                matter_id=result.citation.matter_id,
                document_id=result.citation.document_id,
                version_id=result.citation.version_id,
                title=result.citation.title,
                chunk_index=result.citation.chunk_index,
            ),
            sparse_score=result.sparse_score,
            vector_score=result.vector_score,
            rerank_score=result.rerank_score,
        )
        for index, result in enumerate(ordered)
    )


def build_answer_packet(
    vault_root: Path,
    question: str,
    *,
    matter_id: str | None = None,
    top_k: int = 5,
) -> RagAnswerPacket:
    """Build a grounded context packet for a later LLM generation boundary."""

    results = retrieve_context(vault_root, question, matter_id=matter_id, top_k=top_k)
    grounded_context = "\n\n".join(
        f"[{result.citation.citation_id}] {result.chunk.text}" for result in results
    )
    safety_notice = (
        "Use only the cited local context. If the cited context is insufficient, say so."
        if results
        else "No local context retrieved. Do not answer from model memory."
    )
    return RagAnswerPacket(
        question=question,
        grounded_context=grounded_context,
        citations=tuple(result.citation for result in results),
        retrieval_results=results,
        safety_notice=safety_notice,
    )


def chunk_text(
    text: str,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[str, ...]:
    words = text.split()
    if not words:
        return ()
    if chunk_words <= overlap_words:
        raise RagError("chunk_words must be greater than overlap_words")
    chunks: list[str] = []
    step = chunk_words - overlap_words
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + chunk_words]).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
    return tuple(chunks)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_chunks (
            chunk_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            title TEXT NOT NULL,
            document_type TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            vector_json TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunk_fts USING fts5(
            chunk_id UNINDEXED,
            matter_id UNINDEXED,
            title,
            document_type,
            lifecycle_status,
            text,
            content='rag_chunks',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS rag_chunks_ai AFTER INSERT ON rag_chunks BEGIN
            INSERT INTO rag_chunk_fts(
                rowid, chunk_id, matter_id, title, document_type, lifecycle_status, text
            )
            VALUES (
                new.rowid, new.chunk_id, new.matter_id, new.title, new.document_type,
                new.lifecycle_status, new.text
            );
        END;

        CREATE TRIGGER IF NOT EXISTS rag_chunks_ad AFTER DELETE ON rag_chunks BEGIN
            INSERT INTO rag_chunk_fts(
                rag_chunk_fts, rowid, chunk_id, matter_id, title,
                document_type, lifecycle_status, text
            )
            VALUES (
                'delete', old.rowid, old.chunk_id, old.matter_id, old.title,
                old.document_type, old.lifecycle_status, old.text
            );
        END;
        """
    )


def _document_version_rows(
    connection: sqlite3.Connection,
    *,
    matter_id: str | None,
) -> list[sqlite3.Row]:
    query = """
        SELECT dv.version_id, dv.document_id, dv.extracted_text, dv.lifecycle_status,
               d.matter_id, d.title, d.document_type
        FROM document_versions dv
        JOIN documents d ON d.document_id = dv.document_id
    """
    params: tuple[str, ...] = ()
    if matter_id is not None:
        query += " WHERE d.matter_id = ?"
        params = (matter_id,)
    return list(connection.execute(query, params).fetchall())


def _candidate_rows(
    connection: sqlite3.Connection,
    *,
    matter_id: str | None,
) -> list[sqlite3.Row]:
    if matter_id is None:
        return list(connection.execute("SELECT * FROM rag_chunks").fetchall())
    return list(
        connection.execute(
            "SELECT * FROM rag_chunks WHERE matter_id = ?",
            (matter_id,),
        ).fetchall()
    )


def _row_to_chunk(row: sqlite3.Row) -> ContextChunk:
    return ContextChunk(
        chunk_id=str(row["chunk_id"]),
        matter_id=str(row["matter_id"]),
        document_id=str(row["document_id"]),
        version_id=str(row["version_id"]),
        title=str(row["title"]),
        document_type=str(row["document_type"]),
        lifecycle_status=str(row["lifecycle_status"]),
        chunk_index=int(row["chunk_index"]),
        text=str(row["text"]),
    )


def _sparse_score(query_terms: tuple[str, ...], text: str) -> float:
    if not query_terms:
        return 0.0
    text_terms = Counter(_tokenize(text))
    matches = sum(1 for term in set(query_terms) if text_terms[term] > 0)
    return matches / len(set(query_terms))


def _hashed_vector(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIMENSIONS
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMENSIONS
        direction = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += direction
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    similarity = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    return max(0.0, similarity)


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in re.findall(r"[a-zA-Z0-9]+", text))


def _chunk_id(version_id: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{version_id}:{chunk_index}:{text}".encode()).hexdigest()
    return digest[:32]


def _database_path(vault_root: Path) -> Path:
    return vault_root / "vault.sqlite"


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
