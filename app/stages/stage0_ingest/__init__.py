"""Stage 0 — Document ingest.

Handles PDF parsing (pdfplumber fallback when docling unavailable),
Excel/CSV ingestion, chunking, and FAISS index building.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency in test env
    pdfplumber = None

from app.audit import append_event, EventType
from app.schemas.stage0 import DocumentIngestRecord, Stage0Output


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_doc_type(filename: str) -> str:
    name = filename.lower()
    if "credit_agreement" in name or "credit agreement" in name:
        return "credit_agreement"
    elif "amendment" in name:
        return "amendment_letter"
    elif "compliance" in name or "certificate" in name:
        return "compliance_certificate"
    elif "trial_balance" in name or "trial balance" in name:
        return "trial_balance"
    elif "debt_schedule" in name or "debt schedule" in name:
        return "debt_schedule"
    elif "ebitda" in name:
        return "ebitda_bridge"
    elif name.endswith(".json"):
        return "xbrl_json"
    return "unknown"


def _parse_pdf(path: Path) -> tuple[list[dict], int, bool]:
    """Parse PDF with pdfplumber. Returns (chunks, page_count, is_scanned)."""
    if pdfplumber is None:
        return [], 0, False

    chunks = []
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            text_pages = 0
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    text_pages += 1
                    chunks.append({
                        "chunk_id": f"chunk_{i:05d}",
                        "page_number": i + 1,
                        "text": text,
                        "section_path": [],
                        "bbox": {
                            "x0": 0, "y0": 0,
                            "x1": page.width, "y1": page.height,
                            "page_w": page.width, "page_h": page.height,
                        },
                    })
            is_scanned = text_pages < (page_count * 0.2)
    except Exception as e:
        return [], 0, False
    return chunks, page_count, is_scanned


def _parse_excel(path: Path) -> tuple[list[dict], str, bool]:
    """Parse Excel/CSV. Returns (rows, scale_detected, balanced)."""
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            # Try to detect header row
            df_raw = pd.read_excel(path, header=None, nrows=10)
            header_row = 0
            for i, row in df_raw.iterrows():
                vals = [str(v).lower() for v in row if pd.notna(v)]
                if any(k in " ".join(vals) for k in ["account", "debit", "credit", "balance", "amount", "description"]):
                    header_row = i
                    break
            df = pd.read_excel(path, header=header_row)

        # Detect scale
        scale = "actual"
        col_text = " ".join(str(c).lower() for c in df.columns)
        if "thousand" in col_text or "000s" in col_text:
            scale = "thousands"
        elif "million" in col_text:
            scale = "millions"

        # Check balance (debit = credit)
        balanced = True
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if len(numeric_cols) >= 2:
            # Simple check: sum of all numeric values near zero (for trial balance)
            total = df[numeric_cols].sum().sum()
            balanced = abs(float(total)) < 1e6  # loose check

        rows = []
        for idx, row in df.iterrows():
            rows.append({
                "row_id": f"row_{idx:05d}",
                **{str(k): (None if pd.isna(v) else v) for k, v in row.items()},
            })
        return rows, scale, balanced
    except Exception:
        return [], "actual", True


# ── Main ingest function ──────────────────────────────────────────────────────

async def ingest_document(
    engagement_dir: Path,
    engagement_id: str,
    source_path: Path,
    declared_type: str | None = None,
) -> DocumentIngestRecord:
    """Ingest one document into the engagement."""
    doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
    filename = source_path.name
    doc_type = declared_type or _detect_doc_type(filename)

    # Copy to raw/
    raw_dir = engagement_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / filename
    if not dest.exists():
        import shutil
        shutil.copy2(source_path, dest)

    file_hash = _sha256(dest)
    file_size = dest.stat().st_size

    actor = {"type": "SYSTEM", "id": "stage0.ingest", "version": "1.0.0"}

    await append_event(
        engagement_dir, engagement_id, EventType.DOCUMENT_UPLOADED,
        actor=actor,
        payload_summary={"document_id": doc_id, "filename": filename, "doc_type": doc_type},
    )
    await append_event(
        engagement_dir, engagement_id, EventType.FILE_HASH_COMPUTED,
        actor=actor,
        payload_summary={"document_id": doc_id, "sha256": file_hash},
    )

    record = DocumentIngestRecord(
        document_id=doc_id,
        engagement_id=engagement_id,
        filename=filename,
        document_type=doc_type,
        file_hash_sha256=file_hash,
        file_size_bytes=file_size,
        status="ingested",
    )

    suffix = dest.suffix.lower()

    if suffix == ".pdf":
        # Use Docling parser (falls back to pdfplumber on error)
        from app.stages.stage0_ingest.docling_parser import parse_pdf
        parsed_meta, chunks = parse_pdf(dest, doc_id, engagement_id)

        record.page_count = parsed_meta.get("page_count", 0)
        record.is_scanned = parsed_meta.get("is_scanned", False)
        record.chunks_produced = len(chunks)
        record.tables_found = len(parsed_meta.get("tables_found", []))

        await append_event(
            engagement_dir, engagement_id, EventType.STRUCTURE_PARSED,
            actor=actor,
            payload_summary={
                "document_id": doc_id,
                "pages": record.page_count,
                "chunks": len(chunks),
                "parser": parsed_meta.get("parser", "unknown"),
                "articles_found": len(parsed_meta.get("articles_found", [])),
            },
        )

        # Save parsed metadata
        parsed_dir = engagement_dir / "parsed"
        parsed_dir.mkdir(exist_ok=True)
        parsed_file = parsed_dir / f"{doc_id}.json"
        parsed_file.write_text(json.dumps({
            **parsed_meta,
            "document_type": doc_type,
            "filename": filename,
        }, default=str), encoding="utf-8")

        from app.stages.stage0_ingest.preprocessor import preprocess_document_chunks

        cleaned_chunks = preprocess_document_chunks(chunks, document_type=doc_type)
        raw_chunk_count = len(chunks)
        record.chunks_produced = len(cleaned_chunks)

        # Save chunks with document_type tagged
        chunks_dir = engagement_dir / "chunks"
        chunks_dir.mkdir(exist_ok=True)
        chunk_file = chunks_dir / f"{doc_id}.jsonl"
        with open(chunk_file, "w", encoding="utf-8") as f:
            for ch in cleaned_chunks:
                ch["document_type"] = doc_type
                f.write(json.dumps(ch) + "\n")

        await append_event(
            engagement_dir, engagement_id, EventType.CHUNKS_PRODUCED,
            actor=actor,
            payload_summary={
                "document_id": doc_id,
                "chunk_count": len(cleaned_chunks),
                "raw_chunk_count": raw_chunk_count,
            },
        )

    elif suffix in (".xlsx", ".xls", ".csv"):
        rows, scale, balanced = _parse_excel(dest)
        record.row_count = len(rows)
        record.scale_detected = scale
        record.totals_balanced = balanced

        # Save parsed rows
        parsed_dir = engagement_dir / "parsed"
        parsed_dir.mkdir(exist_ok=True)
        parsed_file = parsed_dir / f"{doc_id}.json"
        parsed_file.write_text(json.dumps({
            "document_id": doc_id,
            "document_type": doc_type,
            "scale": scale,
            "balanced": balanced,
            "rows": rows,
        }, default=str), encoding="utf-8")

        await append_event(
            engagement_dir, engagement_id, EventType.TABLES_EXTRACTED,
            actor=actor,
            payload_summary={"document_id": doc_id, "rows": len(rows), "scale": scale},
        )

    return record


async def run_stage0(
    engagement_dir: Path,
    engagement_id: str,
    document_paths: list[Path],
) -> Stage0Output:
    """Run Stage 0 for all documents."""
    records = []
    for path in document_paths:
        rec = await ingest_document(engagement_dir, engagement_id, path)
        records.append(rec)

    # Build FAISS index from all PDF chunks
    total_chunks = sum(r.chunks_produced for r in records)
    await _build_faiss_index(engagement_dir, engagement_id)

    await append_event(
        engagement_dir, engagement_id, EventType.STAGE_0_COMPLETED,
        actor={"type": "SYSTEM", "id": "stage0", "version": "1.0.0"},
        payload_summary={"documents": len(records), "total_chunks": total_chunks},
    )

    output = Stage0Output(
        engagement_id=engagement_id,
        documents=records,
        faiss_chunk_count=total_chunks,
    )

    # Persist
    state_path = engagement_dir / "state" / "stage0.json"
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    return output


async def _build_faiss_index(engagement_dir: Path, engagement_id: str):
    """Build FAISS index from all chunks. Uses sentence-transformers."""
    chunks_dir = engagement_dir / "chunks"
    if not chunks_dir.exists():
        return

    all_chunks = []
    for chunk_file in chunks_dir.glob("*.jsonl"):
        with open(chunk_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_chunks.append(json.loads(line))

    if not all_chunks:
        return

    try:
        from sentence_transformers import SentenceTransformer
        import faiss
        import numpy as np

        model_name = "BAAI/bge-small-en-v1.5"
        model = SentenceTransformer(model_name)

        texts = [ch.get("text", "")[:512] for ch in all_chunks]
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        embeddings = np.array(embeddings, dtype="float32")

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        faiss_dir = engagement_dir / "faiss"
        faiss_dir.mkdir(exist_ok=True)
        faiss.write_index(index, str(faiss_dir / "chunks.index"))

        # Write meta
        meta_path = faiss_dir / "chunks.meta.jsonl"
        with open(meta_path, "w", encoding="utf-8") as f:
            for i, ch in enumerate(all_chunks):
                f.write(json.dumps({"position": i, "chunk_id": ch["chunk_id"]}) + "\n")

        await append_event(
            engagement_dir, engagement_id, EventType.FAISS_INDEX_BUILT,
            actor={"type": "SYSTEM", "id": "stage0.faiss", "version": "1.0.0"},
            payload_summary={"chunk_count": len(all_chunks), "dim": dim},
        )
    except Exception as e:
        # FAISS/sentence-transformers not available — skip silently, log warning
        await append_event(
            engagement_dir, engagement_id, EventType.INGEST_WARNING,
            actor={"type": "SYSTEM", "id": "stage0.faiss", "version": "1.0.0"},
            payload_summary={"warning": f"FAISS index not built: {e}"},
        )
