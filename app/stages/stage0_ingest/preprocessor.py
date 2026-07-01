"""Utilities for cleaning noisy document chunks before downstream extraction.

The goal is to preserve audit-relevant evidence while removing formatting noise,
repeated headers, empty values, and duplicate content that increases token usage
without changing the underlying facts.
"""
from __future__ import annotations

import re
from typing import Any

COVENANT_CONTEXT_RE = re.compile(
    r"\b("
    r"ebitda|consolidated|borrower|lender|covenant|leverage|coverage|ratio|"
    r"indebtedness|debt|interest|liquidity|capital|threshold|compliance|"
    r"certificate|definition|defined|addback|fixed charge"
    r")\b",
    re.IGNORECASE,
)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_noise(line: str) -> bool:
    """Return True when a line is formatting noise rather than substantive content."""
    if not line:
        return True

    line = line.strip()
    if not line:
        return True

    if re.fullmatch(r"[-=_*•]{3,}", line):
        return True

    if re.fullmatch(r"page\s+\d+(?:\s+of\s+\d+)?", line, re.IGNORECASE):
        return True

    if re.fullmatch(r"\d+\s*(?:of|/)\s*\d+", line):
        return True

    if not re.search(r"[A-Za-z0-9$%]", line):
        return True

    return False


def _looks_like_repeated_header(line: str) -> bool:
    """Return True for short repeated labels that add no covenant context."""
    if re.search(r"\d|[$%]|[.:;]", line):
        return False
    if COVENANT_CONTEXT_RE.search(line):
        return False
    return len(line.split()) <= 8


def _clean_lines(text: str) -> list[str]:
    """Clean a chunk's raw text line-by-line while preserving substantive text."""
    cleaned_lines: list[str] = []
    seen_lines: set[str] = set()
    normalized_lines = [
        _normalize_whitespace(raw_line)
        for raw_line in (text or "").splitlines()
    ]
    line_counts: dict[str, int] = {}
    for line in normalized_lines:
        if not line:
            continue
        line_key = line.lower()
        line_counts[line_key] = line_counts.get(line_key, 0) + 1

    for line in normalized_lines:
        if not line:
            continue

        if _looks_like_noise(line):
            continue

        line_key = line.lower()
        if line_counts.get(line_key, 0) > 1 and _looks_like_repeated_header(line):
            continue

        if line_key in seen_lines:
            continue

        seen_lines.add(line_key)
        cleaned_lines.append(line)

    return cleaned_lines


def _canonical_text(text: str) -> str:
    return _normalize_whitespace(text).lower()


def preprocess_document_chunks(
    chunks: list[dict[str, Any]],
    document_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return a cleaned chunk list with duplicate and noisy content removed.

    The function preserves the original chunk structure while replacing ``text``
    with a compact, audit-ready version. The original raw text is stored in
    ``raw_text`` so downstream audit evidence can still be traced if needed.
    """
    cleaned_chunks: list[dict[str, Any]] = []
    retained_signatures: dict[str, int] = {}

    for chunk in chunks:
        raw_text = chunk.get("raw_text") or chunk.get("text", "") or ""
        cleaned_lines = _clean_lines(raw_text)
        cleaned_text = "\n\n".join(cleaned_lines).strip()

        if not cleaned_text:
            continue

        # Preserve the original content for traceability, but use the compact
        # version for downstream extraction and prompt construction.
        cleaned_chunk = dict(chunk)
        cleaned_chunk["raw_text"] = raw_text
        cleaned_chunk["text"] = cleaned_text
        cleaned_chunk["text_length_chars"] = len(cleaned_text)
        cleaned_chunk["tokens_estimate"] = max(1, len(cleaned_text) // 4)
        cleaned_chunk["preprocessed"] = True
        cleaned_chunk["document_type"] = chunk.get("document_type") or document_type or "unknown"

        signature = _canonical_text(cleaned_text)
        if signature in retained_signatures:
            survivor = cleaned_chunks[retained_signatures[signature]]
            survivor["deduplication_reason"] = "duplicate_content"
            survivor.setdefault("duplicate_chunk_ids", [])
            survivor["duplicate_chunk_ids"].append(chunk.get("chunk_id", ""))
            continue

        retained_signatures[signature] = len(cleaned_chunks)
        cleaned_chunks.append(cleaned_chunk)

    return cleaned_chunks
