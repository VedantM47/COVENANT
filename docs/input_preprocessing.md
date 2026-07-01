# Input preprocessing for audit-ready context

## What changed
- Added a reusable chunk preprocessor in [app/stages/stage0_ingest/preprocessor.py](app/stages/stage0_ingest/preprocessor.py).
- Wired the cleaner into Stage 0 ingestion so persisted chunk files are written in compact form.
- Applied the same cleaning pass in Stage 1 before the extraction and validation pipeline consumes chunks.

## Why it changed
The repository’s downstream LLM extraction and validation logic consumes chunk text directly. The raw parsed content often contains repeated headers, page markers, decorative separators, and duplicated clauses that add noise without adding new audit facts. This preprocessing step reduces token usage while preserving the substantive values needed for extraction.

## How relevance is determined
The preprocessor uses repository-inferred evidence patterns:
- removes blank and decorative lines,
- drops repeated lines and repeated whole chunks,
- preserves numbers, dates, thresholds, and covenant language,
- keeps the original raw text for audit traceability in a separate field.

## Optimizations performed
- Avoids sending duplicate chunk content to the LLM prompt builder.
- Keeps the logic small and deterministic.
- Preserves backward compatibility by keeping the original chunk shape intact and only enriching it with preprocessed fields.

## Verified limitations
The repository does not provide a fully structured clause parser for every document type, so the preprocessor remains conservative and evidence-based rather than using speculative business rules.
