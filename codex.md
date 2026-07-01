# Codex Project Notes

## Current Working State

This repository is a covenant compliance audit platform with a FastAPI backend and a Vite/React frontend.

Verified on this machine:

- Backend imports successfully with the current Python environment after installing the missing `reportlab`, `hypothesis`, and `python-multipart` packages.
- Backend is running at `http://127.0.0.1:8000`.
- Backend health check works: `GET /health` returns `{"ok": true}`.
- Frontend dependencies are installed under `frontend/node_modules`.
- Frontend production build works with `npm run build`.
- Frontend dev server is running at `http://127.0.0.1:5173`.
- Frontend proxies `/api` requests to `http://localhost:8000` through `frontend/vite.config.ts`.
- The new input preprocessor focused tests pass: `python -m pytest tests/unit/test_input_preprocessor.py -q`.
- Python syntax compilation passes: `python -m compileall app -q`.

## Important Environment Notes

The project declares `requires-python = "==3.11.*"` in `pyproject.toml`.

The current machine shell is using Python 3.13.0. A full `python -m pip install -r requirements.txt` does not complete under Python 3.13 because some pinned packages, including `faiss-cpu==1.8.0.post1`, are not available for this interpreter.

Several tests and defaults assume `D:\covenant`. This session is running from:

```powershell
C:\Users\imved\OneDrive\Desktop\COVENANT
```

For local runs from this workspace, set `COVENANT_ROOT` to a writable folder in the repo. The currently started backend uses:

```powershell
C:\Users\imved\OneDrive\Desktop\COVENANT\.codex_run\runtime
```

## Input Preprocessing Changes

The previous agent added a preprocessing layer at:

```text
app/stages/stage0_ingest/preprocessor.py
```

It removes repeated formatting noise, blank/decorative lines, page markers, and duplicate whole chunks while preserving original text in `raw_text`.

I rechecked and corrected the risky parts:

- Short audit terms such as `EBITDA` are preserved.
- Repeated plain headers such as `Credit Agreement` can still be removed.
- Duplicate chunk tracking now marks the actual surviving chunk.
- Stage 0 records the cleaned chunk count that is actually persisted.
- Stage 1 now filters credit agreement and amendment chunks after preprocessing, so classification, defined-term extraction, LLM prompt construction, and source lookup use the same cleaned chunk set.

## Commands To Set Up From Fresh Clone

Use Python 3.11, not Python 3.13.

```powershell
Set-Location "C:\Users\imved\OneDrive\Desktop\COVENANT"

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Set-Location frontend
npm install
Set-Location ..
```

## Commands To Start The Complete Project

Terminal 1, backend:

```powershell
Set-Location "C:\Users\imved\OneDrive\Desktop\COVENANT"
.\.venv\Scripts\Activate.ps1
$env:COVENANT_ROOT = "$PWD\.runtime"
$env:LLM_PROVIDER = "mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2, frontend:

```powershell
Set-Location "C:\Users\imved\OneDrive\Desktop\COVENANT\frontend"
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

API health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Commands Used In This Session

Backend was started with a workspace runtime root:

```powershell
$env:COVENANT_ROOT = "C:\Users\imved\OneDrive\Desktop\COVENANT\.codex_run\runtime"
$env:LLM_PROVIDER = "mock"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend was started with:

```powershell
.\frontend\node_modules\.bin\vite.cmd --host 127.0.0.1 --port 5173
```

Logs for the running servers are here:

```text
.codex_run\backend.log
.codex_run\frontend.log
```

## Validation Results

Passed:

```powershell
python -m pytest tests/unit/test_input_preprocessor.py -q
python -m compileall app -q
npm run build
```

Partially blocked in the current environment:

```powershell
python -m pytest tests/unit -q
```

The unit suite collected and ran, but five tests failed because the suite assumes `D:\covenant` exists or uses it as a subprocess working directory. This is an environment/path issue in this session, not a failure from the preprocessing changes.

## Useful URLs

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
Health:   http://127.0.0.1:8000/health
```

## Frontend Demo Data

The frontend now includes a preloaded demo engagement so the dashboard is useful even when the backend has no saved engagements yet.

Demo data lives here:

```text
frontend/src/demoData.ts
```

What it adds:

- A sample engagement named `FirstBank Holdings LLC`.
- Demo borrower, lender, audit team, gate statuses, and pipeline status.
- A small sample audit trail showing engagement creation, document upload, cleaned chunk counts, clause classification, and a mock LLM call.
- A `Demo` badge on the dashboard.
- A demo banner in the workspace.
- Backend actions are disabled for the demo engagement because it is frontend-only sample data.

The frontend API client uses this demo data when:

- the backend returns an empty engagement list,
- the backend is temporarily unavailable while loading the dashboard,
- the user opens the demo engagement directly,
- the user opens the demo audit trail.

## What This Project Does

This project automates financial covenant compliance audit testing for private-credit or lending engagements.

At a high level, it:

1. Creates an audit engagement for a borrower, lender, loan, and test date.
2. Accepts source documents such as credit agreements, amendments, compliance certificates, trial balances, debt schedules, EBITDA bridges, and regulatory/XBRL data.
3. Parses documents into chunks and structured rows.
4. Cleans noisy document chunks before extraction so repeated headers, empty lines, decorative text, page markers, and duplicate chunks do not waste LLM context.
5. Extracts covenant clauses and defined terms from credit agreements.
6. Uses an LLM provider or mock replay provider to extract structured covenant rules from source chunks.
7. Verifies that extracted source text appears in the claimed source chunk.
8. Normalizes accounting inputs and reconstructs LTM values.
9. Calculates covenant ratios deterministically with symbolic/rational arithmetic.
10. Reconciles computed results against borrower-reported compliance certificate values.
11. Records audit events in an append-only hash-chained audit log.
12. Supports gate approvals and sign-offs through the API/frontend workflow.
13. Produces evidence/seal artifacts for audit documentation.

The key idea is that LLMs are used for extraction and interpretation, but the actual covenant math is designed to be deterministic and auditable.

## Important Backend Files

```text
app/main.py
```

FastAPI application entrypoint. It wires together the API routers and exposes `/health`.

```text
app/settings.py
```

Central runtime settings. Important because `COVENANT_ROOT` controls where engagements, logs, models, cache, and temporary files are written.

```text
app/api/engagements.py
```

Creates, retrieves, and lists engagements.

```text
app/api/documents.py
```

Handles document upload into an engagement.

```text
app/api/pipeline.py
```

Starts the full stage pipeline for an engagement.

```text
app/api/gates.py
```

Handles gate approvals and sign-offs.

```text
app/api/audit.py
```

Returns audit events and verifies the audit hash chain.

```text
app/stages/runner.py
```

Pipeline orchestrator. Runs Stage 0 through Stage 5 in order.

```text
app/stages/stage0_ingest/__init__.py
```

Stage 0 document ingestion. Copies source files, parses PDFs/Excel/CSV, writes parsed chunks, and builds the FAISS index when dependencies are available.

```text
app/stages/stage0_ingest/docling_parser.py
```

PDF parsing layer. Uses Docling when available and falls back to pdfplumber.

```text
app/stages/stage0_ingest/preprocessor.py
```

Smart input cleaner. Removes formatting noise and duplicate chunk content while preserving audit-relevant covenant terms, dates, thresholds, values, borrower/lender context, and raw text traceability.

```text
app/stages/stage1_extract/__init__.py
```

Stage 1 covenant extraction flow. Loads chunks, applies preprocessing, extracts defined terms, classifies covenant clauses, calls the LLM extractor, validates sources, and applies amendments.

```text
app/stages/stage1_extract/defined_terms.py
```

Builds the defined-term graph used as extraction context.

```text
app/stages/stage1_extract/clause_classifier.py
```

Finds likely covenant clauses using keyword filtering and a zero-shot classifier when available.

```text
app/stages/stage1_extract/llm_extractor.py
```

Builds LLM prompts, calls the configured provider, validates source text matches, and returns structured covenant extraction results.

```text
app/stages/stage1_extract/symbolic_validator.py
```

Runs validation checks over extracted covenants, including source verification, formula evaluability, term resolution, period coverage, cap consistency, and operator direction.

```text
app/stages/stage2_normalize/__init__.py
```

Normalizes account mappings and LTM financial values used by the calculation stage.

```text
app/stages/stage3_calculate/__init__.py
```

Performs covenant calculations. This is the important deterministic math stage.

```text
app/stages/stage3_calculate/ast_evaluator.py
```

Evaluates formula ASTs with symbolic arithmetic.

```text
app/stages/stage4_reconcile/__init__.py
```

Compares platform-computed covenant results against borrower-reported compliance certificate values.

```text
app/stages/stage5_evidence/__init__.py
```

Produces final evidence/seal outputs.

```text
app/audit/
```

Audit event and hash-chain implementation. Important for evidence integrity.

```text
app/prompts/
```

LLM prompt templates for covenant extraction, amendment diffing, and compliance certificate parsing.

```text
app/schemas/
```

Pydantic data models for API requests/responses and stage outputs.

```text
app/llm_providers/
```

Provider abstraction and implementations for mock, replay, Gemini, Anthropic, Bedrock, OpenRouter, and related LLM integrations.

## Important Frontend Files

```text
frontend/src/App.tsx
```

Frontend route map.

```text
frontend/src/api/client.ts
```

Frontend API wrapper. This now also falls back to demo data for empty/offline dashboard states.

```text
frontend/src/demoData.ts
```

Preloaded frontend-only sample engagement and audit events.

```text
frontend/src/pages/DashboardPage.tsx
```

Engagement list page. Shows real backend engagements or the preloaded demo engagement.

```text
frontend/src/pages/NewEngagementPage.tsx
```

Form for creating a new backend engagement.

```text
frontend/src/pages/EngagementWorkspacePage.tsx
```

Main engagement workspace. Shows borrower, status, gates, upload controls, and pipeline controls.

```text
frontend/src/pages/AuditTrailPage.tsx
```

Audit event viewer.

```text
frontend/src/types/api.ts
```

TypeScript types mirroring backend API schemas.

```text
frontend/vite.config.ts
```

Vite config. Proxies frontend `/api` requests to the FastAPI backend on port `8000`.

## Important Test And Data Files

```text
tests/unit/test_input_preprocessor.py
```

Focused tests for the smart input preprocessor.

```text
tests/unit/
```

Backend unit tests.

```text
tests/integration/
```

Integration and golden-path tests for sample engagements.

```text
test_inputs/
```

Sample engagement input documents used by tests and manual runs.

```text
reference_inputs/
```

Reference source files and fixture inputs.

```text
tests/fixtures/llm_responses/
```

Mock replay LLM responses used to avoid live LLM calls during deterministic tests.

## How Data Moves Through The System

```text
Frontend
  -> FastAPI API
  -> Engagement folder under COVENANT_ROOT
  -> Stage 0 ingest
  -> Stage 0 chunk preprocessing
  -> Stage 1 covenant extraction
  -> Stage 2 normalization
  -> Stage 3 deterministic calculation
  -> Stage 4 reconciliation
  -> Stage 5 evidence/seal
  -> Audit hash-chain events throughout
```

The most sensitive handoff is between Stage 0/Stage 1 and the LLM extractor. The preprocessor reduces token-heavy noise there, but it stays conservative: if information could affect an audit decision, the cleaner keeps it.

## Extraction Constraints Used In This Project

The main extraction constraints are defined by:

```text
app/prompts/covenant_extraction_v1.md
app/prompts/amendment_diff_v1.md
app/config/ast_grammar.yaml
app/stages/stage1_extract/llm_extractor.py
app/stages/stage1_extract/symbolic_validator.py
app/stages/stage0_ingest/preprocessor.py
```

The covenant extractor is constrained to:

- Extract only from provided engagement metadata, covenant chunks, resolved defined terms, and schedule chunks.
- Return structured JSON matching the supplied schema.
- Avoid invented business logic, invented terms, or invented covenant text.
- Preserve exact numbers and never paraphrase numeric values.
- Include a `source_chunk_id` and verbatim `source_text_match` for extracted fields.
- Use source text that is literally present in the claimed chunk.
- Set optional fields to `null` when the agreement is silent.
- Set `needs_review = true` and provide `review_reason` when a required field cannot be confidently determined.
- Preserve exact threshold values such as `5.00:1.00`, dollar caps such as `$25,000,000`, and percentages such as `10%`.
- Preserve and normalize dates, especially threshold period start/end dates.
- Never guess covenant operator polarity. Phrases like `shall not exceed`, `not greater than`, and equivalent max language map to `<=`; phrases like `at least` and `not less than` map to `>=`.
- Extract every step-down schedule period separately.
- Treat conditional non-date threshold triggers as review items rather than guessing dates.
- Reference formula terms by existing `term_id` values from resolved terms.
- Mark the covenant for review when a used term is not in the resolved term list.
- Detect caps including percent-of-term caps, dollar caps, and greater-of caps.
- Mark circular caps as circular so Stage 3 can solve symbolically.
- Apply override language such as `Notwithstanding the foregoing`.

The amendment extractor is constrained to:

- Read amendment chunks and base agreement context.
- Extract each amendment change.
- Identify the section being modified.
- Identify the change type, such as threshold change, definition change, term addition, or term removal.
- Preserve exact before/after values and source chunk IDs.

The formula extraction is constrained by a closed AST grammar:

- Allowed formula node kinds include literals, references, binary operations, min/max, abs, pow, if, sum-period, percent caps, dollar caps, greater-of caps, and lesser-of caps.
- Allowed comparison operators are `<`, `<=`, `==`, `>=`, and `>`.
- Allowed boolean condition forms are `and`, `or`, and `not`.
- Formula references must use term IDs instead of free-form account names.

The source verification layer enforces:

- Every `source_text_match` must appear as a substring of the claimed chunk after whitespace normalization.
- Extraction results with missing or failed source verification are marked for review.
- Validation checks are emitted as audit events.

The preprocessing layer is constrained to be conservative:

- Remove blank lines, decorative separators, page markers, repeated plain headers, and duplicate whole chunks.
- Preserve dates, numbers, thresholds, covenant values, borrower/lender context, covenant language, and short audit terms such as `EBITDA`.
- Store the original text in `raw_text` so traceability is not lost.
- Keep slightly more text when relevance is uncertain.

## Frontend Tech Stack

The frontend is a Vite React app.

Main technologies:

- React 18 for UI components.
- TypeScript for typed frontend code.
- Vite for local dev server and production build.
- React Router for page routing.
- TanStack React Query for API fetching, caching, polling, and mutation state.
- Axios for HTTP requests to the backend.
- Tailwind CSS for utility-first styling.
- Zustand is present for lightweight client state, though most current pages use React Query directly.
- React PDF is installed for PDF viewing support.
- React Flow is installed for graph/workflow style UI support.

Frontend scripts:

```powershell
Set-Location frontend
npm run dev
npm run build
npm run preview
npm run type-check
```

## How The Frontend Works

The frontend entrypoint is:

```text
frontend/src/App.tsx
```

It creates a React Query client and defines routes:

```text
/                         -> DashboardPage
/engagements/new          -> NewEngagementPage
/engagements/:id          -> EngagementWorkspacePage
/engagements/:id/audit    -> AuditTrailPage
```

The API wrapper is:

```text
frontend/src/api/client.ts
```

It uses Axios with:

```text
baseURL: /api/v1
```

During local development, Vite proxies frontend `/api` calls to the backend:

```text
frontend/vite.config.ts
```

The proxy target is:

```text
http://localhost:8000
```

So the browser talks to the Vite dev server on port `5173`, and Vite forwards API calls to FastAPI on port `8000`.

Page behavior:

- `DashboardPage` calls `listEngagements()` with React Query and refreshes every 5 seconds.
- If the backend has no engagements, the API client returns the frontend demo engagement from `frontend/src/demoData.ts`.
- `NewEngagementPage` posts form data to the backend to create a real engagement.
- `EngagementWorkspacePage` loads one engagement by ID, shows borrower details, pipeline status, gate status, upload controls, and pipeline controls.
- `AuditTrailPage` loads audit events and lets the user filter by event type/category.
- The demo engagement is frontend-only, so pipeline start, upload, and approval actions are disabled for it.

Frontend data flow:

```text
React page
  -> React Query hook
  -> frontend/src/api/client.ts
  -> Vite /api proxy
  -> FastAPI backend /api/v1
  -> COVENANT_ROOT engagement files
  -> response back to React Query cache
  -> UI re-renders
```

Frontend files to understand first:

```text
frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/demoData.ts
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/NewEngagementPage.tsx
frontend/src/pages/EngagementWorkspacePage.tsx
frontend/src/pages/AuditTrailPage.tsx
frontend/src/types/api.ts
frontend/vite.config.ts
frontend/package.json
```
