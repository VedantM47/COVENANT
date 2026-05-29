# KNOWN_LIMITATIONS.md
Generated: 2026-05-29

This file documents every active shortcut, fallback, and v2 deferral in the current build.

---

## v1 Shipping Constraints

1. **v1 ships with hand-authored LLM mock responses; real Gemini extraction was rate-limited and not exercised end-to-end. Real Gemini calls deferred to v1.5.**
2. **Frontend pages 5–11 not implemented** (Rule Review with PDF overlay, Mapping Review, Exception Investigation, Sign-off, Audit Trail filterable, Evidence Pack viewer).
3. **RAG endpoint not implemented.**
4. **GLiNER and Docling running in fallback mode** due to onnxruntime DLL conflict on this Windows machine.
5. **Audit chain LLM_CALL_MADE events for v1 carry provider=mock_replay**; v1.5 will replace these with real Gemini calls.

---

## Active Fallbacks (running in production code path)

### Docling → pdfplumber fallback
**File:** `app/stages/stage0_ingest/__init__.py`
**Condition:** Docling's layout model fails to load due to DLL initialization error (torch/onnxruntime conflict).
**Effect:** PDFs parsed with pdfplumber. Chunks are page-level text blocks, not structural tree nodes.

### GLiNER → regex fallback
**File:** `app/stages/stage1_extract/__init__.py`
**Condition:** GLiNER fails to load due to same onnxruntime DLL error.
**Effect:** Defined-terms extraction uses regex patterns only.

### mock_replay is the v1 default LLM provider
**File:** `app/config/llm.yaml` (test profile)
**Effect:** All tests and demo runs use cached mock responses. No real Gemini calls. `miss_behaviour: raise` ensures no silent fallback.

---

## Not Implemented (v2 deferrals)

- FFIEC/EDGAR/FDIC external API clients (Stage 4 is two-way match only)
- RAG query endpoint (FAISS index built but not queryable via API)
- Frontend: 7 of 11 pages missing (Documents, Pipeline, RuleReview, MappingReview, ExceptionInvestigation, SignOff, EvidencePack)
- Sign-off chain does not enforce roles or distinct users
- Evidence pack PDF is minimal (no recalculation workbook, no clickable source citations)
- RFC 3161 trusted timestamps (TSA call attempted but not validated)
- Stress test at 10+ concurrent engagements
