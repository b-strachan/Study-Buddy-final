from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from app.core.session_store import CourseVectorIndex, get_course_index, get_or_build_course_index, put_course_index
from app.services.moodle_api_client import MoodleAPIError, fetch_course_materials

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

try:
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    VECTOR_SIZE = embedding_model.get_embedding_dimension()
except Exception as exc:
    logger.error("Failed to load embedding model %s: %s", EMBEDDING_MODEL_NAME, exc)
    raise

TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=100,
    separators=["\n\n", "\n", " ", ""],
)


def chunk_text(
    text: str,
    source_name: str,
    course_id: str,
    visibility: str = "student",
    module_name: str | None = None,
    moodle_url: str | None = None,
    section_name: str | None = None,
    origin: str = "upload"
) -> List[Dict[str, Any]]:
    """Split text into chunks and attach the metadata needed for citations."""
    chunks = TEXT_SPLITTER.split_text(text)
    chunk_data: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk_data.append(
            {
                "content": chunk,
                "source": source_name,
                "module_name": module_name or source_name,
                "moodle_url": moodle_url,
                "section_name": section_name,
                "course_id": course_id,
                "visibility": visibility,
                "origin": origin,
            }
        )

    return chunk_data


def _build_index_from_documents(
    documents: List[Dict[str, Any]],
    course_id: str,
    visibility: str = "student",
) -> CourseVectorIndex:
    all_chunks: list[dict[str, Any]] = []

    for document in documents:
        text = document.get("text")
        if not text:
            continue

        document_visibility = document.get("visibility", visibility)
        all_chunks.extend(
            chunk_text(
                text=text,
                source_name=document.get("source", "Unknown"),
                course_id=course_id,
                visibility=document_visibility,
                module_name=document.get("module_name"),
                moodle_url=document.get("moodle_url"),
                section_name=document.get("section_name"),
                origin=document.get("origin", "upload"),
            )
        )

    if not all_chunks:
        return CourseVectorIndex(course_id=course_id, chunks=[], embeddings=np.zeros((0, VECTOR_SIZE), dtype=np.float32))

    text_content = [chunk["content"] for chunk in all_chunks]
    embeddings = embedding_model.encode(text_content, show_progress_bar=False, normalize_embeddings=True)
    embeddings_array = np.asarray(embeddings, dtype=np.float32)

    if embeddings_array.ndim == 1:
        embeddings_array = embeddings_array.reshape(1, -1)

    return CourseVectorIndex(course_id=course_id, chunks=all_chunks, embeddings=embeddings_array)


def _merge_indexes(existing_index: CourseVectorIndex, new_index: CourseVectorIndex) -> CourseVectorIndex:
    if not existing_index.chunks:
        return new_index
    if not new_index.chunks:
        return existing_index

    existing_embeddings = np.asarray(existing_index.embeddings, dtype=np.float32)
    new_embeddings = np.asarray(new_index.embeddings, dtype=np.float32)

    if existing_embeddings.size == 0:
        merged_embeddings = new_embeddings
    elif new_embeddings.size == 0:
        merged_embeddings = existing_embeddings
    else:
        merged_embeddings = np.vstack([existing_embeddings, new_embeddings])

    return CourseVectorIndex(
        course_id=existing_index.course_id,
        chunks=[*existing_index.chunks, *new_index.chunks],
        embeddings=merged_embeddings,
    )


def add_documents_to_course(documents: List[Dict[str, Any]], course_id: str, visibility: str = "student") -> int:
    """Embed documents and merge them into the shared course cache."""
    new_index = _build_index_from_documents(documents, course_id, visibility=visibility)
    existing_index = get_course_index(course_id)

    if existing_index is not None:
        merged_index = _merge_indexes(existing_index, new_index)
    else:
        merged_index = new_index

    put_course_index(merged_index)
    logger.info("Cached %s chunks for course %s", len(new_index.chunks), course_id)
    return len(new_index.chunks)


def ensure_course_materials_cached(course_id: str) -> CourseVectorIndex:
    """Fetch Moodle materials on cache miss and keep one shared index per course."""

    def _builder() -> CourseVectorIndex:
        try:
            documents = fetch_course_materials(course_id)
        except MoodleAPIError:
            raise

        return _build_index_from_documents(documents, course_id)

    return get_or_build_course_index(course_id, _builder)


def search_course_knowledge_base(
    query: str,
    course_id: str,
    top_k: int = 4,
    visibility: str = "student",
) -> List[Dict[str, Any]]:
    """Search the shared course index, building it from Moodle if needed."""
    course_index = ensure_course_materials_cached(course_id)

    if not course_index.chunks:
        return []

    embeddings = np.asarray(course_index.embeddings, dtype=np.float32)
    if embeddings.size == 0:
        return []

    filtered_indices = [
        index
        for index, chunk in enumerate(course_index.chunks)
        if chunk.get("visibility", "student") == visibility
    ]

    if not filtered_indices:
        return []

    query_embedding = embedding_model.encode([query], show_progress_bar=False, normalize_embeddings=True)
    query_vector = np.asarray(query_embedding[0], dtype=np.float32)

    filtered_embeddings = embeddings[filtered_indices]
    scores = filtered_embeddings @ query_vector
    ranked_indices = np.argsort(scores)[::-1][:top_k]

    results: list[dict[str, Any]] = []
    for ranked_index in ranked_indices:
        chunk = course_index.chunks[filtered_indices[ranked_index]]
        results.append(
            {
                "content": chunk.get("content", ""),
                "source": chunk.get("source", "Unknown"),
                "module_name": chunk.get("module_name", chunk.get("source", "Unknown")),
                "moodle_url": chunk.get("moodle_url"),
                "section_name": chunk.get("section_name"),
                "score": float(scores[ranked_index]),
            }
        )

    return results
