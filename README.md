# Covenant Compliance Platform v1.0

Audit-grade private-credit covenant compliance substantive testing automation.
PCAOB AS 1105 / ISA 230 / ISA 320 / ISA 505 compliant.

## Location

Everything lives at `D:\covenant\`. Nothing on C: drive.

## Quick Start

```powershell
# Activate venv
Set-Location D:\covenant
.\.venv\Scripts\Activate.ps1

# Run all tests
python -m pytest tests/unit/ -q

# Run golden tests (takes ~2.5 min each)
python -m pytest tests/integration/firstbank_golden.py tests/integration/nexus_golden.py -v

# Start API server
uvicorn app.main:app --reload --port 8000

# Start frontend dev server
cd frontend && npm run dev

# Verify a chain
python scripts/verify_chain.py D:\covenant\engagements\<ENG-ID>
```

## Architecture

6-stage pipeline, all on D: drive:

```
Stage 0 — Ingest       (pdfplumber + pandas + FAISS)
Stage 1 — Extract      (LLM extraction with source verification)
Stage 2 — Normalize    (account mapping + LTM reconstruction)
Stage 3 — Calculate    (SymPy exact rational arithmetic — NO FLOAT)
Stage 4 — Reconcile    (3-way match + root-cause diagnosis)
Stage 5 — Seal         (hash chain + RFC 3161 timestamp)
```

## Golden Test Results

| Engagement | Borrower Reported | Platform Computed | Compliant | Verdict |
|---|---|---|---|---|
| FirstBank (ENG-2025-001) | 4.228x | **1.374x** | YES | DISCLOSURE_MISMATCH (2.854x variance) |
| Nexus (ENG-2025-002) | 4.574x | **5.356x** | **NO — BREACH** | HARD_BREACH (>5.00x threshold) |

## Hard Rules (never broken)

1. No LLM in the calculation path — Stage 3 is pure SymPy `Rational`
2. Every extracted value has a `source_chunk_id` with verbatim text match
3. Every stage emits hash-chained audit events (SHA-256, canonical JSON)
4. Stages are gated — Stage N+1 waits for human gate N
5. All files on D: drive — nothing on C:
6. Append-only audit log — sealed engagements are immutable

## Test Coverage

- `app/audit/`: 97%
- `app/stages/stage3_calculate/`: 92%
- `app/schemas/`: 100%
- Overall critical packages: **95%**

## TODO(human-review) markers

None left — all ambiguities resolved deterministically.
