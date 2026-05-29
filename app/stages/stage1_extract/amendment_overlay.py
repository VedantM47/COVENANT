"""Amendment overlay — extract diffs from amendment PDFs and apply chronologically."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

AMENDMENT_PROMPT = """You are a legal analyst reviewing an amendment to a credit agreement.
Extract every change made by this amendment to the base credit agreement.

For each change, identify:
- section_modified: the section of the base agreement being modified (e.g. "Section 7.01(a)")
- change_kind: one of threshold_changed, definition_changed, term_added, term_removed,
  step_down_modified, cure_provision_added, covenant_added, covenant_removed, other
- before_text: the exact text being replaced (verbatim from amendment, or null if addition)
- after_text: the new text (verbatim from amendment)
- effective_date: ISO date string if stated, else null
- source_chunk_id: the chunk_id containing this change

Return JSON: {"changes": [...]}"""


def _call_gemini_amendment(chunks_text: str) -> list[dict]:
    """Call Gemini to extract amendment diffs."""
    import google.generativeai as genai

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=AMENDMENT_PROMPT,
        generation_config={"temperature": 0.0, "max_output_tokens": 2048,
                           "response_mime_type": "application/json"},
    )

    user_prompt = f"AMENDMENT_CHUNKS:\n{chunks_text[:8000]}\n\nReturn the JSON now."
    try:
        response = model.generate_content(user_prompt)
        data = json.loads(response.text)
        return data.get("changes", [])
    except Exception:
        return []


def _regex_extract_changes(chunks: list[dict]) -> list[dict]:
    """Regex fallback: find threshold changes like '4.75:1.00' → '5.00:1.00'."""
    changes = []
    for chunk in chunks:
        text = chunk.get("text", "")
        # Pattern: replacing X with Y
        for m in re.finditer(
            r"replacing\s+['\"]?([\d.]+:[0-9.]+)['\"]?\s+with\s+['\"]?([\d.]+:[0-9.]+)['\"]?",
            text, re.IGNORECASE
        ):
            changes.append({
                "section_modified": chunk.get("section_label_display", ""),
                "change_kind": "threshold_changed",
                "before_text": m.group(1),
                "after_text": m.group(2),
                "effective_date": None,
                "source_chunk_id": chunk.get("chunk_id", ""),
            })
        # Pattern: amended from X to Y
        for m in re.finditer(
            r"amended\s+(?:from\s+)?([\d.]+x?)\s+to\s+([\d.]+x?)",
            text, re.IGNORECASE
        ):
            changes.append({
                "section_modified": chunk.get("section_label_display", ""),
                "change_kind": "threshold_changed",
                "before_text": m.group(1),
                "after_text": m.group(2),
                "effective_date": None,
                "source_chunk_id": chunk.get("chunk_id", ""),
            })
    return changes


def apply_amendment_overlay(
    base_covenants: list[dict],
    amendment_chunks: list[dict],
    amendment_doc_id: str,
    effective_date: str | None = None,
) -> list[dict]:
    """Apply amendment diffs to base covenants. Returns updated covenants list."""
    if not amendment_chunks:
        return base_covenants

    # Try LLM extraction first, fall back to regex
    chunks_text = "\n\n".join(
        f"chunk_id={c['chunk_id']}\n{c['text']}"
        for c in amendment_chunks
    )

    changes = _call_gemini_amendment(chunks_text)
    if not changes:
        changes = _regex_extract_changes(amendment_chunks)

    if not changes:
        return base_covenants

    updated = []
    for cov in base_covenants:
        cov = dict(cov)  # shallow copy
        applied_changes = []

        for change in changes:
            kind = change.get("change_kind", "")
            before = change.get("before_text", "")
            after = change.get("after_text", "")

            if kind == "threshold_changed" and before and after:
                # Try to update threshold values
                for thr in cov.get("thresholds", []):
                    val_cf = thr.get("value") or {}
                    val_display = val_cf.get("value_display", "") if isinstance(val_cf, dict) else ""
                    val_num = val_cf.get("value") if isinstance(val_cf, dict) else None

                    # Check if before_text matches this threshold
                    before_clean = before.replace("x", "").replace(":1.00", "").strip()
                    try:
                        before_float = float(before_clean)
                        after_clean = after.replace("x", "").replace(":1.00", "").strip()
                        after_float = float(after_clean)

                        if val_num is not None and abs(float(val_num) - before_float) < 0.01:
                            old_val = val_num
                            if isinstance(val_cf, dict):
                                val_cf["value"] = after_float
                                val_cf["value_display"] = f"{after_float}x"
                                val_cf["source_chunk_id"] = change.get("source_chunk_id", "")
                                val_cf["source_text_match"] = after
                            applied_changes.append({
                                "change_id": f"chg_{len(applied_changes)+1:03d}",
                                "kind": kind,
                                "field_path": "thresholds[].value",
                                "before": old_val,
                                "after": after_float,
                                "source_chunk_id": change.get("source_chunk_id", ""),
                                "source_text_match": f"{before} → {after}",
                            })
                    except (ValueError, TypeError):
                        pass

        if applied_changes:
            overlay = cov.get("amendment_overlay") or {}
            if isinstance(overlay, dict):
                history = overlay.get("amendment_history", [])
                history.append({
                    "amendment_id": amendment_doc_id,
                    "effective_date": effective_date,
                    "changes_applied_here": applied_changes,
                })
                overlay["applied"] = True
                overlay["amendment_history"] = history
                cov["amendment_overlay"] = overlay

        updated.append(cov)

    return updated
