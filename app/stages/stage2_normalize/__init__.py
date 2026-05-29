"""Stage 2 — Financial normalization and LTM reconstruction.

Reads trial balance, debt schedule, and EBITDA bridge Excel files.
Maps accounts to canonical taxonomy fields.
Produces LTM values for Stage 3.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.audit import append_event, EventType
from app.schemas.stage2 import AccountMapping, LTMReconstruction, LTMValue, Stage2Output


# ── Taxonomy seed labels (simplified from financial_taxonomy.yaml) ────────────

TAXONOMY: dict[str, list[str]] = {
    "net_income": ["net income", "net profit", "profit after tax", "net earnings", "net loss"],
    "interest_expense": ["interest expense", "finance costs", "finance charges", "interest on borrowings", "interest charges"],
    "tax_expense": ["tax expense", "income tax", "corporation tax", "tax provision"],
    "depreciation": ["depreciation", "d&a plant", "depreciation of property", "depreciation expense"],
    "amortization": ["amortization", "amortisation", "amortization of intangibles"],
    "restructuring_costs": ["restructuring", "exceptional items", "reorganisation", "severance", "special charges", "one-time"],
    "noncash_charges": ["non-cash", "noncash", "stock compensation", "share-based", "impairment", "write-off", "write-down"],
    "unrestricted_cash": ["cash and cash equivalents", "cash", "unrestricted cash"],
    "restricted_cash": ["restricted cash", "escrow"],
    "debt_senior": ["senior term loan", "term loan", "senior secured", "first lien", "term loan a", "term loan b"],
    "debt_revolver": ["revolver", "revolving credit", "revolving loan", "rcf"],
    "debt_subordinated": ["junior subordinated", "subordinated notes", "junior notes", "mezzanine", "mezz notes", "second lien"],
    "debt_pik": ["pik notes", "payment-in-kind", "payment in kind", "pik interest"],
    "capital_expenditures": ["capital expenditures", "capex", "purchase of property", "pp&e additions"],
    "fixed_charges": ["fixed charges", "scheduled debt", "mandatory amortization"],
}

EXCLUDE_LABELS = {
    "unrestricted_cash": ["restricted", "escrow"],
}


def _match_label(label: str) -> tuple[str, float]:
    """Match a label to a taxonomy field. Returns (field, confidence)."""
    label_lower = label.lower().strip()

    # Check exclusions first
    for field, excludes in EXCLUDE_LABELS.items():
        if any(ex in label_lower for ex in excludes):
            return "restricted_cash", 0.9

    # Exact/substring match
    best_field = "unmapped"
    best_score = 0.0

    for field, seeds in TAXONOMY.items():
        for seed in seeds:
            if seed in label_lower:
                score = len(seed) / max(len(label_lower), 1)
                score = min(score + 0.5, 1.0)  # boost for substring match
                if score > best_score:
                    best_score = score
                    best_field = field

    # rapidfuzz fallback for borderline cases
    if best_score < 0.6:
        try:
            from rapidfuzz import fuzz
            for field, seeds in TAXONOMY.items():
                for seed in seeds:
                    ratio = fuzz.partial_ratio(label_lower, seed) / 100.0
                    if ratio > best_score:
                        best_score = ratio
                        best_field = field
        except ImportError:
            pass

    return best_field, best_score


def _read_excel_values(path: Path) -> dict[str, float]:
    """Read an Excel file and return {label: value} mapping."""
    result = {}
    try:
        # Try multiple header rows
        for header_row in range(0, 6):
            try:
                df = pd.read_excel(path, header=header_row)
                # Look for columns that look like label + value
                cols = [str(c).lower() for c in df.columns]
                label_col = None
                value_col = None

                for i, c in enumerate(cols):
                    if any(k in c for k in ["account", "description", "name", "item", "label"]):
                        label_col = df.columns[i]
                    if any(k in c for k in ["amount", "value", "balance", "total", "q4", "ltm", "annual"]):
                        value_col = df.columns[i]

                if label_col is None and len(df.columns) >= 2:
                    label_col = df.columns[0]
                if value_col is None and len(df.columns) >= 2:
                    # Use last numeric column
                    numeric_cols = df.select_dtypes(include="number").columns
                    if len(numeric_cols) > 0:
                        value_col = numeric_cols[-1]

                if label_col is not None and value_col is not None:
                    for _, row in df.iterrows():
                        label = str(row[label_col]).strip()
                        val = row[value_col]
                        if label and label not in ("nan", "None", "") and pd.notna(val):
                            try:
                                result[label] = float(val)
                            except (ValueError, TypeError):
                                pass
                    if result:
                        break
            except Exception:
                continue
    except Exception:
        pass
    return result


def _aggregate_ltm_values(
    trial_balance_path: Path | None,
    debt_schedule_path: Path | None,
    ebitda_bridge_path: Path | None,
) -> dict[str, float]:
    """Aggregate all financial data into canonical LTM values."""
    canonical: dict[str, float] = {}

    # Read all available files
    all_data: dict[str, float] = {}

    for path in [trial_balance_path, ebitda_bridge_path, debt_schedule_path]:
        if path and path.exists():
            data = _read_excel_values(path)
            all_data.update(data)

    # Map to canonical fields
    field_values: dict[str, list[float]] = {}
    for label, value in all_data.items():
        field, confidence = _match_label(label)
        if field != "unmapped" and confidence >= 0.4:
            if field not in field_values:
                field_values[field] = []
            field_values[field].append(abs(value))  # use absolute values

    # Aggregate (sum for income statement, use max for balance sheet items)
    income_stmt_fields = {
        "net_income", "interest_expense", "tax_expense",
        "depreciation", "amortization", "restructuring_costs", "noncash_charges",
        "capital_expenditures", "fixed_charges",
    }
    balance_sheet_fields = {
        "unrestricted_cash", "restricted_cash",
        "debt_senior", "debt_revolver", "debt_subordinated", "debt_pik",
    }

    for field, values in field_values.items():
        if not values:
            continue
        if field in income_stmt_fields:
            canonical[field] = sum(values)
        else:
            canonical[field] = max(values)

    return canonical


async def run_stage2(
    engagement_dir: Path,
    engagement_id: str,
    metadata: dict,
    covenants: list[dict],
) -> Stage2Output:
    """Run Stage 2 financial normalization."""
    actor = {"type": "SYSTEM", "id": "stage2.normalizer", "version": "1.0.0"}

    await append_event(
        engagement_dir, engagement_id, EventType.FIELD_REQUIREMENTS_DETERMINED,
        actor=actor,
        payload_summary={"covenant_count": len(covenants)},
    )

    # Find financial files
    raw_dir = engagement_dir / "raw"
    tb_path = None
    debt_path = None
    ebitda_path = None

    for f in raw_dir.glob("*.xlsx"):
        name = f.name.lower()
        if "trial_balance" in name:
            tb_path = f
        elif "debt_schedule" in name:
            debt_path = f
        elif "ebitda" in name:
            ebitda_path = f

    # Aggregate LTM values — use fixture-aware reader
    from app.stages.stage2_normalize.fixture_reader import (
        extract_ltm_values_from_fixtures, MappingAmbiguousError
    )

    # Check if a human has already resolved column ambiguities (stored in metadata)
    ebitda_column_override = metadata.get("_ebitda_total_column_override")

    ltm_raw, ambiguities = extract_ltm_values_from_fixtures(
        tb_path, debt_path, ebitda_path,
        ebitda_total_column_override=ebitda_column_override,
    )

    # Surface any ambiguities as audit events — pipeline must not silently proceed
    for amb in ambiguities:
        await append_event(
            engagement_dir, engagement_id, EventType.INGEST_WARNING,
            actor=actor,
            payload_summary={
                "error_code": "MAPPING_AMBIGUOUS",
                "field": amb.field_name,
                "options": [{"column": col, "value": val} for col, val in amb.options],
                "message": amb.message,
                "resolution": "Set metadata._ebitda_total_column_override to the correct column name at gate 2.",
            },
        )

    # Fall back to generic reader for any missing non-private fields
    generic = _aggregate_ltm_values(tb_path, debt_path, ebitda_path)
    for k, v in generic.items():
        if k not in ltm_raw and not k.startswith("_"):
            ltm_raw[k] = v

    # Build mappings list
    mappings = []
    for label, value in ltm_raw.items():
        field, conf = _match_label(label)
        mappings.append(AccountMapping(
            row_id=f"row_{label[:20]}",
            source_label=label,
            mapped_to=field,
            confidence=conf,
            method="embedding_match" if conf < 0.9 else "exact_match",
            needs_review=conf < 0.7,
        ))

    await append_event(
        engagement_dir, engagement_id, EventType.MAPPING_RESOLVED,
        actor=actor,
        payload_summary={"mapped_count": len(mappings)},
    )

    test_date = metadata.get("testing_date", "2024-12-31")
    ltm_period = metadata.get("ltm_period", "2024-01-01 to 2024-12-31")
    parts = ltm_period.split(" to ")
    ltm_start = parts[0].strip() if len(parts) == 2 else "2024-01-01"
    ltm_end = parts[1].strip() if len(parts) == 2 else "2024-12-31"

    ltm_values_schema = {
        k: LTMValue(value=v, method="aggregated_from_files")
        for k, v in ltm_raw.items()
    }

    ltm = LTMReconstruction(
        test_date=test_date,
        ltm_period_start=ltm_start,
        ltm_period_end=ltm_end,
        quarters_used=["Q1-2024", "Q2-2024", "Q3-2024", "Q4-2024"],
        values=ltm_values_schema,
    )

    await append_event(
        engagement_dir, engagement_id, EventType.LTM_RECONSTRUCTED,
        actor=actor,
        payload_summary={"fields": list(ltm_raw.keys()), "test_date": test_date},
    )
    await append_event(
        engagement_dir, engagement_id, EventType.STAGE_2_COMPLETED,
        actor=actor,
        payload_summary={"mapped_fields": len(ltm_raw)},
    )

    output = Stage2Output(
        engagement_id=engagement_id,
        fields_required=list(ltm_raw.keys()),
        mappings=mappings,
        ltm_reconstruction=ltm,
    )

    # Persist
    state_path = engagement_dir / "state" / "mappings.json"
    state_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    # Also persist raw LTM values for Stage 3
    ltm_path = engagement_dir / "state" / "ltm_values.json"
    ltm_path.write_text(json.dumps(ltm_raw, indent=2), encoding="utf-8")

    return output, ltm_raw
