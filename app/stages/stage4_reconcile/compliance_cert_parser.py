"""Compliance certificate parser.

Parses the borrower's compliance certificate PDF to extract:
- Borrower-asserted covenant ratios
- Borrower's EBITDA components
- Borrower's net debt components
- Signing officer name

This replaces metadata["borrower_reported"] in Stage 4.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


# Patterns to find ratio assertions in compliance certificates
RATIO_PATTERNS = [
    # "Net Leverage Ratio: 4.228x" or "Net Leverage Ratio = 4.228:1.00"
    re.compile(
        r'(?:net\s+leverage|leverage\s+ratio)[^\d]*(\d+\.\d+)\s*(?:x|:1)',
        re.IGNORECASE
    ),
    # "Interest Coverage Ratio: 4.55x"
    re.compile(
        r'(?:interest\s+coverage|coverage\s+ratio)[^\d]*(\d+\.\d+)\s*(?:x|:1)',
        re.IGNORECASE
    ),
    # "Fixed Charge Coverage: 2.026x"
    re.compile(
        r'(?:fixed\s+charge)[^\d]*(\d+\.\d+)\s*(?:x|:1)',
        re.IGNORECASE
    ),
    # "Minimum EBITDA: $131,025,000"
    re.compile(
        r'(?:minimum\s+ebitda|consolidated\s+ebitda)[^\$\d]*\$?([\d,]+)',
        re.IGNORECASE
    ),
]

COVENANT_ID_MAP = {
    "net leverage": "COV-NET-LEVERAGE",
    "leverage ratio": "COV-NET-LEVERAGE",
    "interest coverage": "COV-ICR",
    "coverage ratio": "COV-ICR",
    "fixed charge": "COV-FCCR",
    "minimum ebitda": "COV-MIN-EBITDA",
    "consolidated ebitda": "COV-MIN-EBITDA",
}

DOLLAR_PATTERN = re.compile(r'\$?([\d,]+(?:\.\d+)?)\s*(?:million|M\b)?', re.IGNORECASE)
OFFICER_PATTERN = re.compile(
    r'(?:chief financial officer|cfo|treasurer|controller)[,\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
    re.IGNORECASE
)


def _extract_text_from_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    except Exception:
        return ""


def _parse_dollar(text: str) -> float | None:
    """Parse the first dollar amount from text."""
    m = DOLLAR_PATTERN.search(text)
    if not m:
        return None
    val_str = m.group(1).replace(",", "")
    try:
        val = float(val_str)
        if "million" in text.lower() or "M" in text[m.end():m.end()+2]:
            val *= 1_000_000
        return val
    except ValueError:
        return None


def _parse_dollar_last(text: str) -> float | None:
    """Parse the LAST dollar amount from text (for LTM total lines with multiple values)."""
    matches = list(DOLLAR_PATTERN.finditer(text))
    if not matches:
        return None
    # Take the last match
    m = matches[-1]
    val_str = m.group(1).replace(",", "")
    try:
        val = float(val_str)
        if "million" in text[m.end():m.end()+10].lower() or \
           (m.end() < len(text) and text[m.end():m.end()+2].strip().upper() == "M"):
            val *= 1_000_000
        return val
    except ValueError:
        return None
    if not m:
        return None
    val_str = m.group(1).replace(",", "")
    try:
        val = float(val_str)
        if "million" in text.lower() or "M" in text:
            val *= 1_000_000
        return val
    except ValueError:
        return None


def parse_compliance_certificate(cert_path: Path) -> dict:
    """Parse a compliance certificate PDF.

    Returns dict with:
    - borrower_asserted_ratios: {covenant_id: float}
    - ebitda_components: {field: value}
    - net_debt_components: {field: value}
    - signing_officer: str
    - source_path: str
    - parse_confidence: float
    """
    text = _extract_text_from_pdf(cert_path)
    if not text:
        return {
            "borrower_asserted_ratios": {},
            "ebitda_components": {},
            "net_debt_components": {},
            "signing_officer": None,
            "source_path": str(cert_path),
            "parse_confidence": 0.0,
            "parse_method": "failed",
        }

    ratios: dict[str, float] = {}
    ebitda_components: dict[str, float] = {}
    net_debt_components: dict[str, float] = {}

    # Parse line by line looking for covenant ratio assertions
    # Pattern: "Net Leverage Ratio ... 4.23x ... 5.00x" (reported ratio before threshold)
    lines = text.split("\n")
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        line_lower = line_stripped.lower()

        # Look for lines with covenant names and ratio values
        # The borrower's reported ratio appears BEFORE the threshold
        # e.g. "Net Leverage Ratio (§7.10(a)) COMPLIANT 4.23x ≤ 5.00x"
        # or "Net Leverage Ratio 4.228x"

        cov_id = None
        if "net leverage" in line_lower or "leverage ratio" in line_lower:
            cov_id = "COV-NET-LEVERAGE"
        elif "interest coverage" in line_lower:
            cov_id = "COV-ICR"
        elif "fixed charge" in line_lower:
            cov_id = "COV-FCCR"
        elif "minimum ebitda" in line_lower or "min ebitda" in line_lower:
            cov_id = "COV-MIN-EBITDA"

        if cov_id and cov_id not in ratios:
            # Find all ratio values in this line
            ratio_matches = re.findall(r'(\d+\.\d+)\s*(?:x|:1\.00|:1)', line_stripped, re.IGNORECASE)
            if ratio_matches:
                # The borrower's reported ratio is typically the FIRST ratio on the line
                # (before the threshold)
                try:
                    reported = float(ratio_matches[0])
                    # Sanity check: leverage ratios are typically 0.5x-10x
                    # Coverage ratios are typically 0.5x-10x
                    # Min EBITDA is a dollar amount, not a ratio
                    if 0.1 <= reported <= 15.0:
                        ratios[cov_id] = reported
                except ValueError:
                    pass

        # EBITDA components — prefer borrower-labeled LTM values
        if "net income" in line_lower and "total" not in line_lower:
            val = _parse_dollar(line_stripped)
            if val and val > 1_000_000:
                ebitda_components["net_income"] = val
        elif "interest expense" in line_lower or "finance cost" in line_lower:
            val = _parse_dollar(line_stripped)
            if val and val > 100_000:
                ebitda_components["interest_expense"] = val
        elif ("total consolidated ebitda" in line_lower) or \
             ("consolidated ebitda (ltm" in line_lower) or \
             ("ebitda (borrower" in line_lower and "ltm" in line_lower) or \
             ("total ebitda" in line_lower and "borrower" in line_lower):
            # Use last dollar amount on the line (LTM total, not quarterly)
            val = _parse_dollar_last(line_stripped)
            if val and 10_000_000 < val < 10_000_000_000:
                ebitda_components["total_ebitda"] = val
        elif ("total ebitda" in line_lower or "consolidated ebitda" in line_lower) \
             and "total_ebitda" not in ebitda_components:
            val = _parse_dollar_last(line_stripped)
            if val and 10_000_000 < val < 10_000_000_000:
                ebitda_components["total_ebitda"] = val

        # Net debt components — look for borrower-reported values specifically
        if ("net debt" in line_lower and "borrower" in line_lower) or \
           ("net debt (borrower" in line_lower):
            val = _parse_dollar(line_stripped)
            if val and val > 1_000_000:
                net_debt_components["net_debt"] = val
        elif ("total indebtedness" in line_lower and "borrower" in line_lower) or \
             ("total indebtedness (borrower" in line_lower):
            val = _parse_dollar(line_stripped)
            if val and val > 1_000_000:
                net_debt_components["total_debt"] = val
        elif "unrestricted cash" in line_lower:
            val = _parse_dollar(line_stripped)
            if val and val > 0:
                net_debt_components["cash"] = val

    # Extract signing officer
    signing_officer = None
    m = OFFICER_PATTERN.search(text)
    if m:
        signing_officer = m.group(1).strip()

    confidence = min(1.0, 0.3 + 0.2 * len(ratios) + 0.1 * len(ebitda_components))

    return {
        "borrower_asserted_ratios": ratios,
        "ebitda_components": ebitda_components,
        "net_debt_components": net_debt_components,
        "signing_officer": signing_officer,
        "source_path": str(cert_path),
        "parse_confidence": confidence,
        "parse_method": "pdfplumber_regex",
    }
