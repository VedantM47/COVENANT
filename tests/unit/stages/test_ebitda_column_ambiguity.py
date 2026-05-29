"""Regression test: EBITDA bridge column ambiguity must surface at gate 2.

Tests that when Q4 and LTM Total columns have different values for EBITDA totals,
the pipeline raises MappingAmbiguousError rather than silently guessing.

Also tests that providing the override resolves the ambiguity correctly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.stages.stage2_normalize.fixture_reader import (
    MappingAmbiguousError,
    extract_ltm_values_from_fixtures,
    read_ebitda_bridge,
)


def _make_perturbed_ebitda_bridge(tmp_path: Path, q4_ebitda: float, ltm_ebitda: float) -> Path:
    """Create a synthetic EBITDA bridge where Q4 and LTM Total differ."""
    path = tmp_path / "ebitda_bridge_perturbed.xlsx"

    rows = [
        # Header rows
        ["PERTURBED BORROWER -- EBITDA BRIDGE (LTM 2024)", None, None, None, None, None],
        ["Reconciliation", None, None, None, None, None],
        [None] * 6,
        [None] * 6,
        # Column headers
        ["Line Item", "CA Section", "GL Reference", "Q1-2024", "Q4-2024", "LTM Total"],
        # Component rows (unambiguous — same in both columns)
        ["GAAP Net Income", "--", "GL 4001", 10_000_000, 40_000_000, 40_000_000],
        ["+ Interest Expense", "S1.01(a)", "GL 7001", 5_000_000, 20_000_000, 20_000_000],
        ["+ Income Tax Expense", "S1.01(b)", "GL 8001", 2_000_000, 8_000_000, 8_000_000],
        ["+ D&A Total", "S1.01(c/d)", "GL all", 3_000_000, 12_000_000, 12_000_000],
        # EBITDA total rows — Q4 and LTM differ (the ambiguous case)
        ["EBITDA Before Add-Backs", "--", "--", 20_000_000, q4_ebitda, ltm_ebitda],
        ["  + Restructuring (CORRECT -- circular solved)", "S1.01(f)", "SymPy", 0, 0, 0],
        ["TOTAL EBITDA (CORRECT)", "S1.01", "SymPy", 20_000_000, q4_ebitda, ltm_ebitda],
    ]

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="EBITDA Bridge", index=False, header=False)

    return path


def _make_perturbed_debt_schedule(tmp_path: Path) -> Path:
    """Create a minimal debt schedule."""
    path = tmp_path / "debt_schedule_perturbed.xlsx"
    rows = [
        ["PERTURBED BORROWER -- DEBT SCHEDULE"],
        [None],
        [None],
        [None],
        ["Instrument", "Lender", "Drawn Balance"],
        ["Senior Term Loan", "LendCo", 100_000_000],
        [None],
        ["NET DEBT (Correct)", None, 90_000_000],
        ["NET DEBT (Borrower)", None, 90_000_000],
        ["UNRESTRICTED CASH", None, 10_000_000],
    ]
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Facility Summary", index=False, header=False)
    return path


class TestEBITDAColumnAmbiguity:

    def test_equal_values_no_ambiguity(self, tmp_path):
        """When Q4 and LTM Total agree within 1%, no ambiguity is raised."""
        ebitda_path = _make_perturbed_ebitda_bridge(tmp_path, 80_000_000, 80_400_000)  # 0.5% diff
        debt_path = _make_perturbed_debt_schedule(tmp_path)

        values, ambiguities = extract_ltm_values_from_fixtures(
            None, debt_path, ebitda_path
        )
        assert len(ambiguities) == 0, f"Expected no ambiguity, got: {[a.message for a in ambiguities]}"
        assert "_correct_ebitda" in values or "_base_ebitda" in values

    def test_differing_values_raises_ambiguity(self, tmp_path):
        """When Q4 and LTM Total differ by >1%, MappingAmbiguousError is raised."""
        # Q4=80M, LTM=178.5M — these differ by >100%, clearly ambiguous
        ebitda_path = _make_perturbed_ebitda_bridge(tmp_path, 80_000_000, 178_500_000)
        debt_path = _make_perturbed_debt_schedule(tmp_path)

        values, ambiguities = extract_ltm_values_from_fixtures(
            None, debt_path, ebitda_path
        )

        # Must surface ambiguity — not silently proceed
        assert len(ambiguities) > 0, (
            "Pipeline silently proceeded with ambiguous EBITDA column. "
            "Expected MappingAmbiguousError to be raised."
        )
        amb = ambiguities[0]
        assert "_base_ebitda" in amb.field_name or "ebitda" in amb.field_name.lower()
        # Options must include both column values
        option_values = {v for _, v in amb.options}
        assert 80_000_000 in option_values
        assert 178_500_000 in option_values

    def test_override_ltm_total_resolves_ambiguity(self, tmp_path):
        """Human selects 'LTM Total' — ambiguity resolved, correct value used."""
        ebitda_path = _make_perturbed_ebitda_bridge(tmp_path, 80_000_000, 178_500_000)
        debt_path = _make_perturbed_debt_schedule(tmp_path)

        values, ambiguities = extract_ltm_values_from_fixtures(
            None, debt_path, ebitda_path,
            ebitda_total_column_override="LTM Total",
        )

        assert len(ambiguities) == 0, f"Unexpected ambiguity after override: {[a.message for a in ambiguities]}"
        assert "_base_ebitda" in values
        assert abs(values["_base_ebitda"] - 178_500_000) < 1, (
            f"Expected 178_500_000, got {values['_base_ebitda']}"
        )

    def test_override_q4_resolves_ambiguity(self, tmp_path):
        """Human selects 'Q4-2024' — ambiguity resolved, Q4 value used."""
        ebitda_path = _make_perturbed_ebitda_bridge(tmp_path, 136_444_444, 228_288_888)
        debt_path = _make_perturbed_debt_schedule(tmp_path)

        values, ambiguities = extract_ltm_values_from_fixtures(
            None, debt_path, ebitda_path,
            ebitda_total_column_override="Q4-2024",
        )

        assert len(ambiguities) == 0
        assert "_base_ebitda" in values
        assert abs(values["_base_ebitda"] - 136_444_444) < 1, (
            f"Expected 136_444_444, got {values['_base_ebitda']}"
        )

    def test_ambiguity_message_is_human_readable(self, tmp_path):
        """The ambiguity message must be suitable for display at gate 2."""
        ebitda_path = _make_perturbed_ebitda_bridge(tmp_path, 80_000_000, 178_500_000)
        debt_path = _make_perturbed_debt_schedule(tmp_path)

        _, ambiguities = extract_ltm_values_from_fixtures(None, debt_path, ebitda_path)

        assert len(ambiguities) > 0
        msg = ambiguities[0].message
        # Must contain both values and column names
        assert "LTM Total" in msg or "ltm" in msg.lower()
        assert "Q4-2024" in msg or "q4" in msg.lower()
        assert "80,000,000" in msg or "80000000" in msg or "178,500,000" in msg

    def test_only_ltm_column_no_ambiguity(self, tmp_path):
        """When only LTM Total column exists (no Q4), no ambiguity."""
        path = tmp_path / "ebitda_bridge_ltm_only.xlsx"
        rows = [
            ["BORROWER -- EBITDA BRIDGE"],
            [None],
            [None],
            [None],
            ["Line Item", "CA Section", "GL Reference", "Q1-2024", "LTM Total"],
            ["GAAP Net Income", "--", "GL 4001", 10_000_000, 40_000_000],
            ["EBITDA Before Add-Backs", "--", "--", 20_000_000, 80_000_000],
            ["  + Restructuring (CORRECT -- circular solved)", "S1.01(f)", "SymPy", 0, 0],
            ["TOTAL EBITDA (CORRECT)", "S1.01", "SymPy", 20_000_000, 80_000_000],
        ]
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="EBITDA Bridge", index=False, header=False)

        debt_path = _make_perturbed_debt_schedule(tmp_path)
        values, ambiguities = extract_ltm_values_from_fixtures(None, debt_path, path)

        assert len(ambiguities) == 0
        assert "_base_ebitda" in values
        assert abs(values["_base_ebitda"] - 80_000_000) < 1
