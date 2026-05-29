"""Covenant clause classifier using DeBERTa zero-shot NLI.

Uses MoritzLaurer/deberta-v3-large-zeroshot-v1.1-all-33 to classify each chunk
as financial_maintenance_covenant, incurrence_covenant, reporting_covenant, or other.

Retains candidates with P(financial_maintenance_covenant) >= 0.55.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("HF_HOME", r"D:\covenant\models\hf")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\covenant\models\hf")

MODEL_ID = "MoritzLaurer/deberta-v3-large-zeroshot-v1.1-all-33"

CANDIDATE_LABELS = [
    "financial maintenance covenant",
    "incurrence covenant",
    "reporting covenant",
    "other provision",
]

THRESHOLD = 0.55  # minimum P(financial_maintenance_covenant) to retain

# Fast pre-filter: chunks must contain at least one of these keywords
COVENANT_KEYWORDS = re.compile(
    r'\b(leverage|coverage|ebitda|ratio|covenant|shall not permit|shall maintain|'
    r'net debt|indebtedness|capital ratio|liquidity|fixed charge)\b',
    re.IGNORECASE,
)


def _load_classifier():
    """Load the zero-shot classification pipeline."""
    from transformers import pipeline
    return pipeline(
        "zero-shot-classification",
        model=MODEL_ID,
        device=-1,  # CPU
    )


def _is_toc_chunk(text: str) -> bool:
    """Return True if this chunk looks like a table of contents entry rather than covenant text."""
    # TOC chunks: short lines with section numbers and page numbers
    # They contain "Section X.XX ... NNN" patterns but not actual covenant language
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return False
    # If most lines are short (< 80 chars) and contain page numbers, it's a TOC
    short_lines = sum(1 for l in lines if len(l) < 80)
    has_page_numbers = sum(1 for l in lines if re.search(r'\b\d{1,3}\s*$', l))
    if len(lines) > 3 and short_lines / len(lines) > 0.7 and has_page_numbers > 2:
        return True
    # Docling table items that are TOC tables
    if "self_ref='#/tables/" in text and "Section" in text and "column_header" in text:
        return True
    return False


def classify_covenant_clauses(
    chunks: list[dict],
    classifier=None,
) -> list[dict]:
    """Classify chunks and return candidates with P(financial_maintenance) >= threshold.

    Returns list of candidate dicts with predicted_class, class_probabilities, confidence.
    """
    # Pre-filter by keywords to avoid running the model on every chunk
    # Also skip TOC chunks (they contain section references but not covenant text)
    keyword_candidates = [
        c for c in chunks
        if COVENANT_KEYWORDS.search(c.get("text", ""))
        and len(c.get("text", "")) > 100
        and not _is_toc_chunk(c.get("text", ""))
    ]

    if not keyword_candidates:
        return []

    # Load model if not provided
    if classifier is None:
        try:
            classifier = _load_classifier()
        except Exception as e:
            import warnings
            warnings.warn(f"DeBERTa classifier unavailable: {e}. Using keyword-only classification.")
            # Fallback: return keyword-matched chunks as financial_maintenance candidates
            return [
                {
                    "candidate_id": f"cand_{i:03d}",
                    "chunk_ids": [c["chunk_id"]],
                    "section_label_display": c.get("section_label_display", ""),
                    "page_range": [c.get("page_number", 0), c.get("page_number", 0)],
                    "predicted_class": "financial_maintenance_covenant",
                    "predicted_subtype": _guess_subtype(c.get("text", "")),
                    "class_probabilities": {
                        "financial_maintenance_covenant": 0.60,
                        "incurrence_covenant": 0.10,
                        "reporting_covenant": 0.10,
                        "other": 0.20,
                    },
                    "confidence": 0.60,
                    "needs_review": True,
                    "source": "keyword_fallback",
                }
                for i, c in enumerate(keyword_candidates[:20])  # cap at 20
            ]

    candidates = []
    for i, chunk in enumerate(keyword_candidates[:30]):  # cap at 30 to control cost
        text = chunk.get("text", "")[:512]  # truncate for model
        try:
            result = classifier(text, CANDIDATE_LABELS, multi_label=False)
            probs = dict(zip(result["labels"], result["scores"]))

            # Map to our label names
            fm_score = probs.get("financial maintenance covenant", 0.0)
            inc_score = probs.get("incurrence covenant", 0.0)
            rep_score = probs.get("reporting covenant", 0.0)
            other_score = probs.get("other provision", 0.0)

            if fm_score >= THRESHOLD:
                candidates.append({
                    "candidate_id": f"cand_{i:03d}",
                    "chunk_ids": [chunk["chunk_id"]],
                    "section_label_display": chunk.get("section_label_display", ""),
                    "page_range": [chunk.get("page_number", 0), chunk.get("page_number", 0)],
                    "predicted_class": "financial_maintenance_covenant",
                    "predicted_subtype": _guess_subtype(text),
                    "class_probabilities": {
                        "financial_maintenance_covenant": fm_score,
                        "incurrence_covenant": inc_score,
                        "reporting_covenant": rep_score,
                        "other": other_score,
                    },
                    "confidence": fm_score,
                    "needs_review": fm_score < 0.75,
                    "source": "deberta_zero_shot",
                })
        except Exception:
            continue

    return candidates


def _guess_subtype(text: str) -> str:
    """Guess covenant subtype from text keywords."""
    text_lower = text.lower()
    if "leverage" in text_lower or "net debt" in text_lower:
        return "leverage_ratio_max"
    elif "coverage" in text_lower or "interest" in text_lower:
        return "interest_coverage_min"
    elif "fixed charge" in text_lower:
        return "fixed_charge_coverage_min"
    elif "ebitda" in text_lower and "minimum" in text_lower:
        return "min_ebitda"
    elif "capital" in text_lower and "ratio" in text_lower:
        return "capital_ratio_min"
    return "financial_maintenance_covenant"
