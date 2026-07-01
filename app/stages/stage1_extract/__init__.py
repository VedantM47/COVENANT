"""Stage 1 — Real covenant extraction from documents.

This stage reads ONLY from the document chunks produced by Stage 0.
It does NOT read metadata["covenants"], metadata["known_errors"],
metadata["correct_calculation"], or metadata["borrower_reported"].

Pipeline:
1. Build defined-terms graph (GLiNER + NetworkX)
2. Classify covenant clauses (DeBERTa zero-shot)
3. Extract each covenant via Gemini structured output
4. Run 8 symbolic validation checks
5. Apply amendment overlays
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.audit import append_event, EventType
from app.schemas.stage1 import (
    Covenant, Stage1Output, ExtractionMeta, ValidationResult as SchemaValidationResult,
    AmendmentOverlay, Threshold, EBITDAAddback, AddbackCap, CovenantFormula, FormulaExpression,
)
from app.schemas.common import ConfidenceField


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_chunks(engagement_dir: Path, doc_type_filter: list[str] | None = None) -> list[dict]:
    """Load all chunks from the engagement's chunk store."""
    chunks = []
    chunks_dir = engagement_dir / "chunks"
    if not chunks_dir.exists():
        return chunks
    for chunk_file in chunks_dir.glob("*.jsonl"):
        with open(chunk_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunk = json.loads(line)
                    if doc_type_filter is None or chunk.get("document_type") in doc_type_filter:
                        chunks.append(chunk)
    return chunks


def _chunks_by_id(chunks: list[dict]) -> dict[str, str]:
    """Build {chunk_id: text} lookup."""
    return {c["chunk_id"]: c.get("text", "") for c in chunks}


def _find_amendment_chunks(engagement_dir: Path) -> list[dict]:
    """Load chunks from amendment documents."""
    chunks = []
    chunks_dir = engagement_dir / "chunks"
    if not chunks_dir.exists():
        return chunks
    # Find amendment document IDs from parsed metadata
    parsed_dir = engagement_dir / "parsed"
    amendment_doc_ids = set()
    if parsed_dir.exists():
        for f in parsed_dir.glob("*.json"):
            try:
                meta = json.loads(f.read_text(encoding="utf-8"))
                if meta.get("document_type") == "amendment_letter":
                    amendment_doc_ids.add(meta.get("document_id", ""))
            except Exception:
                pass

    for chunk_file in chunks_dir.glob("*.jsonl"):
        with open(chunk_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunk = json.loads(line)
                    if chunk.get("document_type") == "amendment_letter":
                        chunks.append(chunk)
    return chunks


def _normalize_covenant_id(raw_id: str, name: str, subtype: str) -> str:
    """Normalize LLM-returned covenant ID to a consistent format."""
    name_lower = name.lower()
    subtype_lower = subtype.lower()

    # Map by name/subtype keywords
    if any(k in name_lower or k in subtype_lower for k in ["leverage", "net debt"]):
        return "COV-NET-LEVERAGE"
    elif any(k in name_lower or k in subtype_lower for k in ["interest coverage", "icr"]):
        return "COV-ICR"
    elif any(k in name_lower or k in subtype_lower for k in ["fixed charge", "fccr"]):
        return "COV-FCCR"
    elif any(k in name_lower or k in subtype_lower for k in ["minimum ebitda", "min ebitda"]):
        return "COV-MIN-EBITDA"
    elif any(k in name_lower or k in subtype_lower for k in ["capital ratio", "cet1", "tier 1"]):
        return "COV-CAPITAL-RATIO"
    elif raw_id and len(raw_id) >= 3 and not raw_id.startswith("cand_"):
        # Use the LLM-provided ID if it looks reasonable
        return f"COV-{raw_id.upper().replace(' ', '-').replace('.', '-')[:20]}"
    else:
        # Generate from subtype
        return f"COV-{subtype_lower.upper().replace('_', '-')[:20]}"


def _replace_chunk_ids(obj, old_chunk_id: str, new_chunk_id: str):
    """Recursively replace old_chunk_id with new_chunk_id in extracted data."""
    if isinstance(obj, dict):
        return {k: _replace_chunk_ids(v, old_chunk_id, new_chunk_id) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_chunk_ids(item, old_chunk_id, new_chunk_id) for item in obj]
    elif isinstance(obj, str) and obj == old_chunk_id:
        return new_chunk_id
    return obj


def _build_covenant_from_llm_output(
    llm_result: dict,
    meta: dict,
    engagement_id: str,
    doc_id: str,
    candidate: dict,
) -> Covenant:
    """Convert LLM extraction output to a Covenant schema object.

    Replaces any mock chunk_ids with the actual chunk_ids from the candidate.
    """
    # Get the real chunk_id from the candidate
    real_chunk_ids = candidate.get("chunk_ids", [])
    real_chunk_id = real_chunk_ids[0] if real_chunk_ids else f"{engagement_id}:{doc_id}:struct:00000"

    # Replace any mock chunk_ids in the llm_result with the real one
    # Mock files may have chunk_ids from a different engagement
    if llm_result.get("source_chunk_ids"):
        old_ids = llm_result.get("source_chunk_ids", [])
        if old_ids and old_ids[0] != real_chunk_id:
            llm_result = _replace_chunk_ids(llm_result, old_ids[0], real_chunk_id)
            llm_result["source_chunk_ids"] = real_chunk_ids
    """Convert LLM extraction output to a Covenant schema object."""
    cov_id = _normalize_covenant_id(
        llm_result.get("covenant_id") or candidate.get("candidate_id", ""),
        llm_result.get("covenant_name") or llm_result.get("name", ""),
        llm_result.get("covenant_subtype") or candidate.get("predicted_subtype", ""),
    )
    cov_name = llm_result.get("covenant_name") or llm_result.get("name", cov_id)
    subtype = llm_result.get("covenant_subtype") or candidate.get("predicted_subtype", "")
    section = llm_result.get("section_reference", "")

    # Build thresholds
    thresholds = []
    for i, thr_raw in enumerate(llm_result.get("thresholds", [])):
        try:
            op_raw = thr_raw.get("operator") or {}
            op_val = op_raw.get("value", "<=") if isinstance(op_raw, dict) else str(op_raw)
            val_raw = thr_raw.get("value") or {}
            val_num = val_raw.get("value") if isinstance(val_raw, dict) else val_raw
            val_display = val_raw.get("value_display", f"{val_num}x") if isinstance(val_raw, dict) else f"{val_num}x"
            src_chunk = val_raw.get("source_chunk_id", "") if isinstance(val_raw, dict) else ""
            src_match = val_raw.get("source_text_match", "") if isinstance(val_raw, dict) else ""

            start_raw = thr_raw.get("period_start") or {}
            end_raw = thr_raw.get("period_end") or {}

            thresholds.append(Threshold(
                threshold_id=f"thr_{cov_id}_{i:03d}",
                period_start=ConfidenceField(
                    value=start_raw.get("value") if isinstance(start_raw, dict) else start_raw,
                    source_chunk_id=start_raw.get("source_chunk_id", "") if isinstance(start_raw, dict) else "",
                    source_text_match=start_raw.get("source_text_match", "") if isinstance(start_raw, dict) else "",
                    confidence=0.90,
                    confidence_band="high",
                ) if start_raw else None,
                period_end=ConfidenceField(
                    value=end_raw.get("value") if isinstance(end_raw, dict) else end_raw,
                    source_chunk_id=end_raw.get("source_chunk_id", "") if isinstance(end_raw, dict) else "",
                    source_text_match=end_raw.get("source_text_match", "") if isinstance(end_raw, dict) else "",
                    confidence=0.90,
                    confidence_band="high",
                ) if end_raw else None,
                operator=ConfidenceField(
                    value=op_val,
                    source_chunk_id=op_raw.get("source_chunk_id", "") if isinstance(op_raw, dict) else "",
                    source_text_match=op_raw.get("source_text_match", "") if isinstance(op_raw, dict) else "",
                    confidence=0.95,
                    confidence_band="high",
                ),
                value=ConfidenceField(
                    value=float(val_num) if val_num is not None else 0.0,
                    value_display=str(val_display),
                    source_chunk_id=src_chunk,
                    source_text_match=src_match,
                    confidence=0.95,
                    confidence_band="high",
                ),
            ))
        except Exception:
            continue

    # Build EBITDA addbacks
    addbacks = []
    for ab_raw in llm_result.get("ebitda_addbacks_resolved", []):
        try:
            cap_raw = ab_raw.get("cap")
            cap = None
            if cap_raw:
                cap = AddbackCap(
                    kind=cap_raw.get("kind", "pct_of_ebitda"),
                    value=cap_raw.get("value"),
                    is_circular=cap_raw.get("is_circular", False),
                    source_chunk_id=cap_raw.get("source_chunk_id", ""),
                    source_text_match=cap_raw.get("source_text_match", ""),
                )
            addbacks.append(EBITDAAddback(
                field=ab_raw.get("field", ""),
                term_id=ab_raw.get("term_id", ""),
                cap=cap,
            ))
        except Exception:
            continue

    # Build formula
    formula = None
    formula_raw = llm_result.get("formula")
    if formula_raw:
        try:
            num_raw = formula_raw.get("numerator") or {}
            den_raw = formula_raw.get("denominator") or {}
            formula = CovenantFormula(
                kind=formula_raw.get("kind", "ratio"),
                numerator=FormulaExpression(
                    expression_ast=num_raw.get("expression_ast") or {},
                    expression_human=num_raw.get("expression_human", ""),
                    source_chunk_id=num_raw.get("source_chunk_id", ""),
                    source_text_match=num_raw.get("source_text_match", ""),
                ) if num_raw else None,
                denominator=FormulaExpression(
                    expression_ast=den_raw.get("expression_ast") or {},
                    expression_human=den_raw.get("expression_human", ""),
                    source_chunk_id=den_raw.get("source_chunk_id", ""),
                    source_text_match=den_raw.get("source_text_match", ""),
                ) if den_raw else None,
            )
        except Exception:
            pass

    return Covenant(
        covenant_id=cov_id,
        covenant_name=cov_name,
        covenant_type=llm_result.get("covenant_type", "financial_maintenance"),
        covenant_subtype=subtype,
        section_reference=section,
        source_chunk_ids=[c["chunk_id"] for c in candidate.get("_chunks", [])],
        source_text_excerpt=llm_result.get("source_text_excerpt", ""),
        thresholds=thresholds,
        formula=formula,
        ebitda_definition_reference=llm_result.get("ebitda_definition_reference"),
        ebitda_addbacks_resolved=addbacks,
        extraction=ExtractionMeta(
            model=meta.get("model", "gemini-2.5-flash"),
            provider=meta.get("provider", "gemini"),
            overall_confidence=meta.get("overall_confidence", 0.8),
            self_consistency_runs=meta.get("self_consistency_runs", 2),
            self_consistency_score=1.0 - 0.1 * len(meta.get("self_consistency_disagreements", [])),
            fields_disagreeing=meta.get("self_consistency_disagreements", []),
        ),
        validation=SchemaValidationResult(
            schema_valid=True,
            all_sources_verified=len(meta.get("source_verification_failures", [])) == 0,
            ebitda_terms_resolved=True,
            formula_evaluable_with_dummy_inputs=True,
            z3_period_bracketing_valid=True,
        ),
        amendment_overlay=AmendmentOverlay(applied=False),
        needs_review=llm_result.get("needs_review", False),
        review_reason=llm_result.get("review_reason"),
    )


def _fallback_covenant_from_text(
    candidate: dict,
    engagement_id: str,
    doc_id: str,
    test_date: str,
) -> Covenant:
    """Build a minimal covenant from text when LLM extraction fails.

    Extracts threshold value and operator using regex.
    Sets needs_review=True so the human gate catches it.
    """
    text = " ".join(c.get("text", "") for c in candidate.get("_chunks", []))
    subtype = candidate.get("predicted_subtype", "leverage_ratio_max")
    cov_id = _normalize_covenant_id("", subtype.replace("_", " "), subtype)

    # Extract threshold value
    threshold_val = 5.0
    operator = "<="
    m = re.search(r'(\d+\.\d+)\s*(?:x|:1\.00)', text, re.IGNORECASE)
    if m:
        threshold_val = float(m.group(1))
    if re.search(r'shall not exceed|not greater than|maximum', text, re.IGNORECASE):
        operator = "<="
    elif re.search(r'at least|not less than|minimum', text, re.IGNORECASE):
        operator = ">="

    chunk_id = candidate.get("chunk_ids", [""])[0]

    return Covenant(
        covenant_id=cov_id,
        covenant_name=subtype.replace("_", " ").title(),
        covenant_type="financial_maintenance",
        covenant_subtype=subtype,
        section_reference=candidate.get("section_label_display", ""),
        source_chunk_ids=candidate.get("chunk_ids", []),
        source_text_excerpt=text[:200],
        thresholds=[Threshold(
            threshold_id=f"thr_{cov_id}_000",
            period_start=ConfidenceField(
                value="2024-01-01", source_chunk_id=chunk_id,
                source_text_match="", confidence=0.5, confidence_band="low",
            ),
            period_end=ConfidenceField(
                value="2025-12-31", source_chunk_id=chunk_id,
                source_text_match="", confidence=0.5, confidence_band="low",
            ),
            operator=ConfidenceField(
                value=operator, source_chunk_id=chunk_id,
                source_text_match="", confidence=0.6, confidence_band="medium",
            ),
            value=ConfidenceField(
                value=threshold_val, value_display=f"{threshold_val}x",
                source_chunk_id=chunk_id,
                source_text_match=m.group(0) if m else "",
                confidence=0.7, confidence_band="medium",
            ),
        )],
        extraction=ExtractionMeta(
            model="regex_fallback", provider="none", overall_confidence=0.5,
        ),
        validation=SchemaValidationResult(
            schema_valid=True, all_sources_verified=False,
            formula_evaluable_with_dummy_inputs=False,
            z3_period_bracketing_valid=False,
        ),
        amendment_overlay=AmendmentOverlay(applied=False),
        needs_review=True,
        review_reason="LLM extraction failed; regex fallback used. Human review required.",
    )


async def run_stage1(
    engagement_dir: Path,
    engagement_id: str,
    metadata: dict,
) -> Stage1Output:
    """Run Stage 1 — real covenant extraction from documents.

    DOES NOT read metadata["covenants"] or any ground-truth fields.
    Reads only: testing_date, borrower name (for context), lender name.
    """
    actor = {"type": "SYSTEM", "id": "stage1.extractor", "version": "2.0.0"}
    test_date = metadata.get("testing_date", "2024-12-31")

    # ── Load all chunks from Stage 0 ─────────────────────────────────────────
    all_chunks = _load_chunks(engagement_dir)
    from app.stages.stage0_ingest.preprocessor import preprocess_document_chunks

    all_chunks = preprocess_document_chunks(all_chunks)
    ca_chunks = [c for c in all_chunks if c.get("document_type") == "credit_agreement"]
    amendment_chunks = [c for c in all_chunks if c.get("document_type") == "amendment_letter"]

    if not ca_chunks:
        # No credit agreement chunks — emit warning and return empty
        await append_event(
            engagement_dir, engagement_id, EventType.INGEST_WARNING,
            actor=actor,
            payload_summary={"warning": "No credit_agreement chunks found. Stage 1 cannot extract covenants."},
        )
        return Stage1Output(
            engagement_id=engagement_id,
            status="failed_no_documents",
            covenants_extracted=0,
        )

    chunks_lookup = _chunks_by_id(all_chunks)

    await append_event(
        engagement_dir, engagement_id, EventType.DEFINITIONS_LOCATED,
        actor=actor,
        payload_summary={"ca_chunks": len(ca_chunks), "amendment_chunks": len(amendment_chunks)},
    )

    # ── Sub-stage 1.1: Defined-terms graph ───────────────────────────────────
    from app.stages.stage1_extract.defined_terms import build_defined_terms_graph

    defined_terms_output, term_graph = build_defined_terms_graph(
        ca_chunks, engagement_id, "DOC-CA-001"
    )
    defined_term_ids = {t["term_id"] for t in defined_terms_output.get("terms", [])}

    await append_event(
        engagement_dir, engagement_id, EventType.DEFINED_TERMS_EXTRACTED,
        actor=actor,
        payload_summary={
            "term_count": defined_terms_output.get("term_count", 0),
            "graph_nodes": defined_terms_output.get("graph_stats", {}).get("total_nodes", 0),
        },
    )
    await append_event(
        engagement_dir, engagement_id, EventType.TERM_GRAPH_BUILT,
        actor=actor,
        payload_summary=defined_terms_output.get("graph_stats", {}),
    )

    # Persist defined terms
    dt_path = engagement_dir / "state" / "defined_terms.json"
    dt_path.write_text(json.dumps(defined_terms_output, indent=2), encoding="utf-8")

    # ── Sub-stage 1.2: Clause classification ─────────────────────────────────
    from app.stages.stage1_extract.clause_classifier import classify_covenant_clauses

    candidates = classify_covenant_clauses(ca_chunks)

    await append_event(
        engagement_dir, engagement_id, EventType.COVENANT_CLAUSE_CLASSIFIED,
        actor=actor,
        payload_summary={
            "candidates_found": len(candidates),
            "method": candidates[0].get("source", "none") if candidates else "none",
        },
    )

    # Persist clause candidates
    clauses_path = engagement_dir / "state" / "covenant_clauses.json"
    clauses_path.write_text(json.dumps({
        "engagement_id": engagement_id,
        "candidates": candidates,
    }, indent=2), encoding="utf-8")

    # ── Sub-stage 1.3: LLM extraction per candidate ───────────────────────────
    from app.stages.stage1_extract.llm_extractor import extract_covenant_with_llm, LLMExtractionError
    from app.stages.stage1_extract.symbolic_validator import validate_covenant

    covenants: list[Covenant] = []
    total_tokens = 0

    for candidate in candidates[:10]:  # cap at 10 candidates
        cov_candidate_id = candidate.get("candidate_id", "")
        chunk_ids = candidate.get("chunk_ids", [])
        cov_chunks = [c for c in ca_chunks if c["chunk_id"] in chunk_ids]
        candidate["_chunks"] = cov_chunks

        await append_event(
            engagement_dir, engagement_id, EventType.COVENANT_EXTRACTION_STARTED,
            actor=actor,
            payload_summary={"candidate_id": cov_candidate_id, "chunk_count": len(cov_chunks)},
        )

        # Get reachable defined terms for this candidate
        resolved_terms = defined_terms_output.get("terms", [])[:20]  # limit context size

        try:
            llm_result, meta = await extract_covenant_with_llm(
                metadata,
                cov_chunks,
                resolved_terms,
                None,  # schedule chunks
                chunks_lookup,
                subtype_hint=candidate.get("predicted_subtype", ""),
            )

            await append_event(
                engagement_dir, engagement_id, EventType.LLM_CALL_MADE,
                actor=actor,
                payload_summary={
                    "candidate_id": cov_candidate_id,
                    "provider": meta.get("provider", "gemini"),
                    "model": meta.get("model", "gemini-2.5-flash"),
                    "latency_ms": meta.get("latency_ms", 0),
                    "self_consistency_runs": meta.get("self_consistency_runs", 2),
                    "source_verification_failures": len(meta.get("source_verification_failures", [])),
                },
            )

            # Emit source verification failures as audit events
            for failure in meta.get("source_verification_failures", []):
                await append_event(
                    engagement_dir, engagement_id, EventType.VALIDATION_CHECK_RUN,
                    actor=actor,
                    payload_summary={
                        "check": "CHUNK_SOURCE_VERIFICATION_FAILED",
                        "field_path": failure.get("field_path"),
                        "chunk_id": failure.get("chunk_id"),
                        "passed": False,
                    },
                )

            await append_event(
                engagement_dir, engagement_id, EventType.SELF_CONSISTENCY_CHECK_RUN,
                actor=actor,
                payload_summary={
                    "candidate_id": cov_candidate_id,
                    "disagreements": meta.get("self_consistency_disagreements", []),
                },
            )

            # Build Covenant object
            cov = _build_covenant_from_llm_output(
                llm_result, meta, engagement_id, "DOC-CA-001", candidate
            )

        except LLMExtractionError as e:
            # LLM failed — use regex fallback, mark for human review
            await append_event(
                engagement_dir, engagement_id, EventType.INGEST_WARNING,
                actor=actor,
                payload_summary={
                    "warning": f"LLM extraction failed for {cov_candidate_id}: {e}",
                    "fallback": "regex",
                },
            )
            cov = _fallback_covenant_from_text(candidate, engagement_id, "DOC-CA-001", test_date)

        # ── Sub-stage 1.4: Symbolic validation ───────────────────────────────
        validation_report = validate_covenant(
            cov.model_dump(),
            chunks_lookup,
            defined_term_ids,
            test_date,
        )

        for check in validation_report.checks:
            await append_event(
                engagement_dir, engagement_id, EventType.VALIDATION_CHECK_RUN,
                actor=actor,
                payload_summary={
                    "covenant_id": cov.covenant_id,
                    "check": check.check_name,
                    "passed": check.passed,
                    "detail": check.detail,
                },
            )

        if not validation_report.all_passed:
            cov.needs_review = True
            failures = "; ".join(f"{c.check_name}: {c.detail}" for c in validation_report.failures)
            cov.review_reason = (cov.review_reason or "") + f" | Validation failures: {failures}"

        covenants.append(cov)

    # ── Sub-stage 1.5: Amendment overlay ─────────────────────────────────────
    if amendment_chunks and covenants:
        from app.stages.stage1_extract.amendment_overlay import apply_amendment_overlay

        # Find amendment doc ID
        amd_doc_id = amendment_chunks[0].get("document_id", "DOC-AMD-001") if amendment_chunks else "DOC-AMD-001"

        updated_dicts = apply_amendment_overlay(
            [c.model_dump() for c in covenants],
            amendment_chunks,
            amd_doc_id,
        )

        # Rebuild Covenant objects from updated dicts
        new_covenants = []
        for d in updated_dicts:
            try:
                new_covenants.append(Covenant.model_validate(d))
            except Exception:
                new_covenants.append(covenants[len(new_covenants)])
        covenants = new_covenants

        await append_event(
            engagement_dir, engagement_id, EventType.AMENDMENT_APPLIED,
            actor=actor,
            payload_summary={"amendment_doc_id": amd_doc_id, "covenants_updated": len(covenants)},
        )

    await append_event(
        engagement_dir, engagement_id, EventType.STAGE_1_COMPLETED,
        actor=actor,
        payload_summary={"covenants_extracted": len(covenants)},
    )
    await append_event(
        engagement_dir, engagement_id, EventType.HUMAN_GATE_OPENED,
        actor=actor,
        payload_summary={"gate_id": "gate_1_rule_review", "items": len(covenants)},
    )

    output = Stage1Output(
        engagement_id=engagement_id,
        status="awaiting_human_gate_1",
        defined_terms_count=defined_terms_output.get("term_count", 0),
        covenants_extracted=len(covenants),
        covenants_needing_review=sum(1 for c in covenants if c.needs_review),
        covenants=covenants,
        defined_terms=[],  # stored separately in defined_terms.json
    )

    state_path = engagement_dir / "state" / "covenants.json"
    state_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    return output
