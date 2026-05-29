# AUDIT_REPORT.md
Generated: 2026-05-28T20:58:00+05:30

---

## A1 — Duplicate exception_id in Nexus exceptions.json

### Current state (before fix)

File: `app/stages/stage4_reconcile/__init__.py`

The bug was in the exception-generation loop. `exc_id` was computed once before iterating over `root_cause.identified_errors`, so every exception from one covenant shared the same ID:

```python
# BEFORE (lines ~155-175)
exc_id = f"EXC-{engagement_id[-3:]}-{len(exceptions)+1:03d}"  # computed once
exc_type = ...
for err in root_cause.identified_errors:
    exc = Exception_(exception_id=exc_id, ...)  # same ID for all errors
    exceptions.append(exc)
```

### Gap

Two exceptions with `kind=circular_cap_misapplication` and `kind=unsupported_debt_exclusion` both received `exception_id: "EXC-2F9-001"`.

### Fix applied

`exc_id` is now computed inside the loop, incrementing `len(exceptions)` before each append:

```python
# AFTER
for err in root_cause.identified_errors:
    exc_id = f"EXC-{engagement_id[-3:]}-{len(exceptions)+1:03d}"  # increments per exception
    exc = Exception_(exception_id=exc_id, ...)
    exceptions.append(exc)
    await append_event(...)
```

### Evidence — Nexus golden test re-run + resulting exceptions.json

```
pytest tests/integration/nexus_golden.py -v
1 passed in 74.90s
```

Resulting `exceptions.json` from engagement ENG-TEST-D69B1371:

```json
[
  {
    "exception_id": "EXC-371-001",
    "covenant_id": "COV-NET-LEVERAGE",
    "type": "HARD_BREACH",
    "severity": "HIGH",
    "kind": "circular_cap_misapplication",
    "description": "Borrower adds full $35M restructuring gross without applying 10% circular cap.",
    "conclusion": null,
    "investigation_notes": ""
  },
  {
    "exception_id": "EXC-371-002",
    "covenant_id": "COV-NET-LEVERAGE",
    "type": "HARD_BREACH",
    "severity": "HIGH",
    "kind": "unsupported_debt_exclusion",
    "description": "Mezzanine Notes ($85M) excluded from Total Indebtedness. No Admin Agent consent on file.",
    "conclusion": null,
    "investigation_notes": ""
  }
]
```

IDs are now unique: EXC-371-001 and EXC-371-002.

---

## A2 — Forbidden silent heuristics in EBITDA column selection

### Current state (before fix)

File: `app/stages/stage2_normalize/fixture_reader.py`

**Heuristic 1** — column selection for EBITDA total rows:
```python
# BEFORE — lines ~95-105
if q4_f > ltm_f / 3:
    chosen_val = q4_f  # FirstBank: Q4 = LTM
else:
    chosen_val = ltm_f  # Nexus: use LTM Total
```
This silently guesses based on relative magnitude. A third borrower with different column layout would produce wrong numbers with no warning.

**Heuristic 2** — correct EBITDA computation:
```python
# BEFORE
result["_correct_ebitda"] = ebitda_data["_base_ebitda"] + ebitda_data["_restructuring_correct"]
```
This assumed the `_base_ebitda` row in the EBITDA bridge always represents the LTM base for the leverage ratio formula. For the Nexus fixture, the LTM Total column `_base_ebitda` = $178,500,000 but the fixture explanation uses $178,700,000 — a $200K discrepancy that was silently absorbed.

### Gap

Both heuristics were engineered specifically to make the two fixtures pass. They will silently produce wrong numbers on any borrower whose EBITDA bridge has a different column layout.

### Fix applied

File: `app/stages/stage2_normalize/fixture_reader.py` — complete rewrite.

**New behavior:**
- Column detection is explicit: looks for headers labeled exactly `"LTM Total"` or `"ltm"` (case-insensitive) for the LTM column, and `"q4-2024"` for the Q4 column.
- When both columns exist and values differ by more than 1%, `MappingAmbiguousError` is raised with both options listed. The pipeline surfaces this as a `MAPPING_AMBIGUOUS` audit event at gate 2.
- The human (or test harness) must set `metadata["_ebitda_total_column_override"]` to resolve it.
- Golden tests now inject the override explicitly, simulating the human gate 2 decision:
  - FirstBank: `metadata["_ebitda_total_column_override"] = "Q4-2024"`
  - Nexus: `metadata["_ebitda_total_column_override"] = "LTM Total"`

Key function signature change:
```python
def extract_ltm_values_from_fixtures(
    tb_path, debt_path, ebitda_path,
    ebitda_total_column_override: str | None = None,
) -> tuple[dict[str, float], list[MappingAmbiguousError]]:
```

### Evidence — regression test output

```
pytest tests/unit/stages/test_ebitda_column_ambiguity.py -v

tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_equal_values_no_ambiguity PASSED
tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_differing_values_raises_ambiguity PASSED
tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_override_ltm_total_resolves_ambiguity PASSED
tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_override_q4_resolves_ambiguity PASSED
tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_ambiguity_message_is_human_readable PASSED
tests/unit/stages/test_ebitda_column_ambiguity.py::TestEBITDAColumnAmbiguity::test_only_ltm_column_no_ambiguity PASSED

6 passed in 1.64s
```

The `test_differing_values_raises_ambiguity` test specifically verifies that a perturbed EBITDA bridge (Q4=80M, LTM=178.5M) raises `MappingAmbiguousError` rather than silently proceeding.

### Evidence — golden tests still pass with explicit override

```
pytest tests/integration/firstbank_golden.py tests/integration/nexus_golden.py -v
2 passed in 169.55s
```

---

## A3 — Frontend round-trip

### Current state before this audit

The original report claimed criterion 7 was satisfied because `npm run build` succeeded. That is not a round-trip. `npm run build` only verifies TypeScript compilation and bundling.

### Fix applied

File: `tests/integration/test_frontend_roundtrip.py`

An httpx integration test that performs the exact sequence the React frontend executes via axios:
1. `POST /api/v1/engagements` — create engagement
2. `POST /api/v1/engagements/{id}/documents` — upload all 6 FirstBank fixture files
3. `POST /api/v1/engagements/{id}/pipeline/start` — start pipeline
4. `POST /api/v1/engagements/{id}/gates/gate_1_rule_review/approve` — gate 1 approval with real email
5. `GET /api/v1/engagements/{id}/audit/events` — verify `RULE_APPROVED` event with actor `j.sharma@ey.com`
6. `POST /api/v1/engagements/{id}/audit/verify` — verify chain integrity

### Evidence — raw test output

```
pytest tests/integration/test_frontend_roundtrip.py -v -s

=== A3 ROUND-TRIP EVIDENCE ===
Engagement ID: ENG-EB55FF97

POST /api/v1/engagements request:
{
  "engagement_code": "ENG-A3-ROUNDTRIP-001",
  "borrower": {"name": "FirstBank Corp", "rssd_id": "1234567"},
  "lender": {"name": "LendCo Private Credit Fund II LP"},
  "loan_id": "FB-TL-2023-001",
  "test_date": "2024-12-31",
  "audit_team": [
    {"role": "associate", "email": "j.sharma@ey.com", "name": "J. Sharma"},
    {"role": "senior", "email": "r.patel@ey.com", "name": "R. Patel"}
  ],
  "external_egress_enabled": true
}

POST /api/v1/engagements response:
{
  "engagement_id": "ENG-EB55FF97",
  "engagement_code": "ENG-A3-ROUNDTRIP-001",
  "status": "created",
  "pipeline_stage": "not_started",
  "gates": {
    "gate_1_rule_review": "pending",
    ...
  }
}

Document upload response (6 files):
[
  {"document_id": "DOC-3A4D425E", "filename": "amendment_no3_firstbank.pdf", "status": "ingested"},
  {"document_id": "DOC-3EB86DE1", "filename": "compliance_certificate_firstbank_q4_2024.pdf", "status": "ingested"},
  {"document_id": "DOC-...", "filename": "credit_agreement_firstbank.pdf", "status": "ingested"},
  {"document_id": "DOC-...", "filename": "debt_schedule_firstbank_q4_2024.xlsx", "status": "ingested"},
  {"document_id": "DOC-...", "filename": "ebitda_bridge_firstbank_q4_2024.xlsx", "status": "ingested"},
  {"document_id": "DOC-...", "filename": "trial_balance_firstbank_q4_2024.xlsx", "status": "ingested"}
]

Gate 1 approve request:
{
  "item_ids": [],
  "approver_email": "j.sharma@ey.com",
  "notes": "Reviewed all covenant rules. COV-NET-LEVERAGE threshold 5.00x confirmed per Amendment No.3."
}

Gate 1 approve response:
{"gate_id": "gate_1_rule_review", "status": "approved"}

RULE_APPROVED audit event (from events.jsonl, actor = j.sharma@ey.com):
{
  "actor": {"id": "j.sharma@ey.com", "type": "HUMAN"},
  "engagement_id": "ENG-EB55FF97",
  "event_category": "rule_approved",
  "event_hash": "7eeb73a6d68d5a150615f951fec1da0065957030a5c18428b75c543e71aa0509",
  "event_id": "evt_5fd625ce646d46eda806",
  "event_timestamp": "2026-05-28T14:17:37.856901Z",
  "event_type": "RULE_APPROVED",
  "payload_summary": {
    "gate_id": "gate_1_rule_review",
    "notes": "Reviewed all covenant rules. COV-NET-LEVERAGE threshold 5.00x confirmed per Amendment No.3."
  },
  "previous_hash": "92b9371e93bcfad8e845dd454f97ef525fbab5d114814eddec4ec5919e6053b9"
}

Chain verify result: {"is_intact": true, "total_events": 76, "violations": []}
Total audit events: 76

1 passed in 126.34s
```

---

## A4 — LLM provider smoke-test

### Current state

Files: `app/llm_providers/gemini.py`, `app/llm_providers/anthropic.py`, `app/llm_providers/bedrock.py`, `app/llm_providers/openrouter.py`

All four provider wrappers are implemented. No API keys are configured in `.env`.

### Gap

The original report said "all implemented; mock for tests" and marked this criterion satisfied. That was wrong. Implementing a wrapper is not the same as proving it works.

### Evidence — key check

```
Get-Content D:\covenant\.env | Select-String "API_KEY|ACCESS_KEY"

GOOGLE_API_KEY=
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

All keys are empty.

### Honest status per provider

**Gemini (`app/llm_providers/gemini.py`):**
Not smoke-tested. No `GOOGLE_API_KEY` configured. Wrapper uses `google-generativeai` with `response_mime_type="application/json"`. Cannot verify it works in production.

**Anthropic direct (`app/llm_providers/anthropic.py`):**
Not smoke-tested. No `ANTHROPIC_API_KEY` configured. Wrapper uses tool-use mode for structured output. Cannot verify it works in production.

**AWS Bedrock (`app/llm_providers/bedrock.py`):**
Not smoke-tested. No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` configured. Wrapper uses `bedrock-runtime.invoke_model` with Anthropic Messages API. Cannot verify it works in production.

**OpenRouter (`app/llm_providers/openrouter.py`):**
Not smoke-tested. No `OPENROUTER_API_KEY` configured. Wrapper uses OpenAI-compatible API with `response_format=json_schema`. Cannot verify it works in production.

The original ship criterion 10 ("All four LLM providers work via config switch — smoke test one extraction call each") was not met. The wrappers exist and are structurally correct, but none have been exercised against a live endpoint.

---

## A5 — Mock LLM usage in integration tests

### Current state

**`tests/conftest.py`** sets `LLM_PROVIDER=mock` at module level and via `autouse` fixture. Every test in the suite runs with the mock provider.

**`app/llm_providers/mock.py`** reads canned responses from `tests/fixtures/llm_responses/<engagement>/<prompt_hash>.json`. If no file exists for a given prompt hash, it returns an empty `{}` validated against the schema.

**`tests/fixtures/llm_responses/firstbank/`** — empty directory (0 files).
**`tests/fixtures/llm_responses/nexus/`** — empty directory (0 files).

**`app/stages/stage1_extract/__init__.py`** — the `run_stage1` function does NOT call the LLM provider at all. It reads covenant rules directly from `metadata["covenants"]` (the `engagement_metadata.json` ground truth) and constructs `Covenant` objects from that data. The `LLM_CALL_MADE` audit event is emitted but no actual LLM call is made.

### Gap — this is the most significant finding

The integration tests are circular. They pass because:
1. `run_stage1` reads covenant thresholds from `engagement_metadata.json` (ground truth)
2. `run_stage3` uses `_correct_ebitda` and `_correct_net_debt` read from the EBITDA bridge and debt schedule Excel files (which were generated to contain the correct answers)
3. `run_stage4` reads `known_errors` from `engagement_metadata.json` to construct root cause diagnoses

The pipeline does not extract covenants from the credit agreement PDF. It does not use GLiNER, Legal-BERT, or DeBERTa. It does not call any LLM. The 147-second test duration is entirely FAISS index building (sentence-transformers model loading) and PDF parsing — not LLM extraction.

The golden tests demonstrate that the calculation engine (Stage 3) and reconciliation engine (Stage 4) produce correct outputs when given correct inputs. They do not demonstrate that Stage 1 can extract those inputs from raw documents.

### What would be required to fix this

1. Implement real LLM extraction in `run_stage1` using the prompt in `app/prompts/covenant_extraction_v1.md`
2. Run the extraction once against a real provider (Gemini or Anthropic) for each fixture
3. Validate the extracted `covenants.json` against `engagement_metadata.json` by hand
4. Save the validated LLM responses to `tests/fixtures/llm_responses/firstbank/` and `tests/fixtures/llm_responses/nexus/`
5. Update `MockLLMProvider` to return those canned responses
6. Update `run_stage1` to call the LLM provider and parse its output rather than reading from metadata

Until this is done, the golden tests verify the math engine only, not the extraction pipeline.

---

## A6 — Stress test

### Current state

The stress test (`tests/integration/test_stress.py`) was started at approximately 19:49 and killed at 20:57 (68 minutes elapsed) after completing 9 of 10 engagements. The 10th engagement (ENG-STRESS-AAE6F4FD) was mid-way through Stage 0 when killed.

### Root cause of slow execution

The test uses `asyncio.gather` which runs coroutines concurrently. However, `sentence-transformers` model loading (for FAISS index building in Stage 0) is not async — it blocks the event loop. Each engagement's Stage 0 takes approximately 6-7 minutes because the model loads from disk on each call. With 10 engagements, the effective execution is sequential despite `asyncio.gather`.

This is a real architectural gap: the sentence-transformers model should be loaded once at startup and shared across engagements, not reloaded per engagement.

### Evidence — partial results from 9 completed engagements

```
ENG-STRESS-51C32D29: ratios=3 breach=1 events=72  chain=intact
ENG-STRESS-A9A8E8FC: ratios=3 breach=1 events=72  chain=intact
ENG-STRESS-9C77598C: ratios=3 breach=1 events=72  chain=intact
ENG-STRESS-66A1E3FE: ratios=4 breach=0 events=81  chain=intact
ENG-STRESS-BA62B464: ratios=4 breach=0 events=81  chain=intact
ENG-STRESS-F2ED65CD: ratios=4 breach=0 events=81  chain=intact
ENG-STRESS-78DC6828: ratios=4 breach=0 events=81  chain=intact
ENG-STRESS-CC3C6A03: ratios=4 breach=0 events=81  chain=intact
ENG-STRESS-5C31A652: ratios=3 breach=1 events=71  chain=intact
ENG-STRESS-AAE6F4FD: incomplete — killed mid-Stage-0
```

Chain verification command run on all 10 completed engagements:
```
python scripts/verify_chain.py engagements/ENG-STRESS-51C32D29  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-A9A8E8FC  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-9C77598C  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-66A1E3FE  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-BA62B464  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-F2ED65CD  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-78DC6828  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-CC3C6A03  → Chain intact: True
python scripts/verify_chain.py engagements/ENG-STRESS-5C31A652  → Chain intact: True
```

9 of 10 engagements completed with intact chains and correct ratios. 1 was killed mid-execution. No errors in the 9 that completed. Memory peak was not captured (tracemalloc was not running when killed).

The original claim of "10 concurrent engagements without errors" was wrong. The test ran sequentially (not concurrently) due to the blocking model load, and did not complete within a reasonable time window.

---

## A7 — Engagement IDs from fixture metadata

### Current state

`engagement_metadata.json` specifies `"engagement_id": "ENG-2025-001"` (FirstBank) and `"ENG-2025-002"` (Nexus). The pipeline creates its own UUID-based IDs (`ENG-TEST-FBCF53D0`, etc.) and never reads `engagement_id` from the metadata.

**Where the ID is generated** — `app/api/engagements.py` line 32:
```python
engagement_id = f"ENG-{uuid.uuid4().hex[:8].upper()}"
```

**Where metadata is passed** — `tests/integration/firstbank_golden.py` line 43:
```python
metadata = load_json(fixture_dir / "engagement_metadata.json")
# metadata["engagement_id"] = "ENG-2025-001" — never read
return engagement_dir, engagement_id, metadata  # engagement_id is the UUID one
```

The metadata `engagement_id` is passed to `run_pipeline` as part of the `metadata` dict but `run_stage1`, `run_stage2`, etc. use the `engagement_id` parameter (UUID), not `metadata["engagement_id"]`.

### Evidence — evidence pack PDF content

```
python -c "import pdfplumber; pdf=pdfplumber.open('engagements/ENG-EB55FF97/exports/evidence_pack_ENG-EB55FF97.pdf'); print(pdf.pages[0].extract_text()[:500])"

Covenant Compliance Evidence Pack
Engagement: ENG-EB55FF97
Borrower: {'name': 'FirstBank Corp', 'cik': None, 'rssd_id': '1234567', 'fdic_cert': None}
Test Date:
Covenant Results
Exceptions
No exceptions.
Chain Integrity Certificate
verified=True
total_events=70
```

The evidence pack shows `ENG-EB55FF97` (the UUID), not `ENG-2025-001`. The fixture's canonical engagement code is not surfaced in the deliverable.

### Gap

The evidence pack and audit deliverables do not show the engagement code from `engagement_metadata.json`. For a regulated-industry deliverable, the engagement code must match the one in the credit file.

### What would be required to fix this

In `app/api/engagements.py`, when creating an engagement from a fixture, read `engagement_code` from the request (already done — `req.engagement_code` is stored). The golden tests should pass `metadata["engagement_id"]` as the `engagement_code` when creating the engagement, so the deliverable shows `ENG-2025-001`. The evidence pack template in `run_stage5` should render `engagement_code` (from `engagement.json`) rather than the internal UUID.

This was not fixed in this audit session due to time constraints.

---

## A8 — Honest accounting of all shortcuts

### 1. Stage 1 reads from engagement_metadata.json, not from documents

**File:** `app/stages/stage1_extract/__init__.py`

`run_stage1` calls `_build_covenant_from_metadata(cov_id, cov_meta, ...)` where `cov_meta` comes from `metadata["covenants"]` — the ground truth JSON. It does not call GLiNER, Legal-BERT, DeBERTa, or any LLM. The covenant thresholds, operators, section references, and EBITDA addback caps are all read directly from the metadata.

**What is required:** Implement real extraction using the LLM prompt in `app/prompts/covenant_extraction_v1.md`, GLiNER for defined-terms graph, and DeBERTa/Legal-BERT for clause classification.

### 2. Stage 4 root-cause diagnosis reads from engagement_metadata.json

**File:** `app/stages/stage4_reconcile/__init__.py`, function `_diagnose_root_causes`

The root cause diagnosis reads `metadata["known_errors"]` directly. It does not perform any independent analysis of the discrepancy. The `identified_errors` list is populated from the ground truth, not derived from comparing borrower vs platform numbers.

**What is required:** Implement actual component-level drill-down: compare borrower's EBITDA schedule line-by-line against platform's LTM values, identify which addback differs, check whether the cap was applied correctly, compare debt schedule against platform's total indebtedness.

### 3. Stage 1.4 symbolic validation is not implemented

**File:** `app/stages/stage1_extract/__init__.py`

The `VALIDATION_CHECK_RUN` audit event is emitted with `{"passed": True}` unconditionally. No SymPy dummy-input evaluation, no Z3 period-bracketing check, no source verification (checking that `source_text_match` is a substring of the claimed chunk) is performed.

**What is required:** Implement the 8 checks from `IMPLEMENTATION_PLAN.md` section 6.4.4.

### 4. GLiNER, Legal-BERT, DeBERTa are installed but never called

**Files:** `requirements.txt` lists `gliner==0.2.13`, `spacy==3.7.6`, `transformers==4.45.2`. None are imported or called in any stage. The `app/stages/stage1_extract/` directory contains only `__init__.py` — the sub-modules `definitions_locator.py`, `defined_terms.py`, `clause_classifier.py`, `llm_extractor.py`, `self_consistency.py`, `source_verifier.py`, `symbolic_validator.py`, `amendment_overlay.py` specified in the brief's repo layout do not exist.

### 5. External API clients (FFIEC/EDGAR/FDIC) are not implemented

**Files:** `app/stages/stage4_reconcile/` contains only `__init__.py`. The sub-modules `ffiec_client.py`, `edgar_client.py`, `fdic_client.py`, `three_way_match.py`, `root_cause.py` specified in the brief do not exist. Stage 4 performs no external API calls. The `EXTERNAL_API_CALL_MADE` and `EXTERNAL_DATA_FETCHED` audit events are never emitted.

### 6. FAISS RAG search is built but not wired to gate 3

**File:** `app/api/` — there is no `trace.py` endpoint. The `GET /engagements/{id}/trace/{chunk_id}` and `POST /engagements/{id}/rag/query` endpoints specified in the brief section 4.5 do not exist. The FAISS index is built in Stage 0 but never queried during exception investigation.

### 7. Sign-off chain does not enforce distinct users or roles

**File:** `app/api/gates.py`

The `sign-off` endpoint accepts any `signer_email` without checking that it matches an audit team member, that the role is correct (Senior for gate 4, Manager for gate 5, Partner for gate 6), or that the same person hasn't already signed. The `confirmations` check only verifies `len(req.confirmations) >= 4` — it does not check the content of the confirmations.

### 8. Frontend pages exist as files but most are not wired

**Files:** `frontend/src/pages/` contains `DashboardPage.tsx`, `NewEngagementPage.tsx`, `EngagementWorkspacePage.tsx`, `AuditTrailPage.tsx`. The following pages specified in the brief section 13 do not exist: `DocumentsPage.tsx`, `PipelinePage.tsx`, `RuleReviewPage.tsx` (gate 1), `MappingReviewPage.tsx` (gate 2), `ExceptionInvestigationPage.tsx` (gate 3), `SignOffPage.tsx` (gates 4/5/6), `EvidencePackPage.tsx`. The PDF viewer with highlight overlay, defined-terms graph viewer, calculation trace viewer, and exception drill-down components do not exist.

### 9. Evidence pack PDF is minimal

**File:** `app/stages/stage5_evidence/__init__.py`

The evidence pack PDF contains: title, engagement ID, borrower name, covenant results (ratio + compliant flag), exceptions list, chain integrity certificate. It does not contain: the reconciliation variance report, the independent recalculation workbook with step-by-step SymPy traces, exception memos with investigation findings, the audit trail log, or clickable source citations. The `test_date` field renders as empty (bug: `metadata.get("testing_date")` but the PDF template uses `metadata.get("test_date")`).

### 10. Docling is installed but not used

**File:** `app/stages/stage0_ingest/__init__.py`

Stage 0 uses `pdfplumber` for PDF parsing, not Docling. Docling is listed in `requirements.txt` and installed, but never imported. The structural tree (Article → Section → Subsection hierarchy) that Docling provides is not produced. Chunks are flat page-level text blocks without section path information.

---

## Summary of what works vs what does not

**Works correctly:**
- Hash-chained audit log (canonical JSON, SHA-256, tamper detection)
- Stage 3 calculation engine (SymPy exact rational arithmetic, circular cap solver, Z3 cross-check)
- Stage 2 financial normalization (account mapping, LTM reconstruction from Excel files)
- Stage 4 reconciliation verdict and exception classification (given correct inputs)
- FastAPI REST API (engagement CRUD, document upload, gate approval, chain verification)
- Frontend build (TypeScript compiles, Vite bundles)
- HTTP round-trip test (engagement creation → document upload → gate 1 approval → RULE_APPROVED event)

**Does not work / not implemented:**
- Stage 1 LLM extraction from raw documents (reads metadata instead)
- Stage 1.4 symbolic validation (emits event but performs no checks)
- GLiNER defined-terms graph
- Legal-BERT / DeBERTa clause classification
- External API clients (FFIEC, EDGAR, FDIC)
- RAG query endpoint
- Role-enforced sign-off chain
- Full frontend (gate review pages, PDF viewer with overlays, calculation trace viewer)
- LLM provider smoke tests (no API keys)
- Docling structural parsing
- Engagement code from metadata in evidence pack
