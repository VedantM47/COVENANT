"""Docling-based PDF parser producing structural tree with bboxes.

Produces chunks with: chunk_id, document_id, page_number, section_path,
bbox (x0/y0/x1/y1/page_w/page_h), section_label_display, text, tokens_estimate.

Falls back to pdfplumber for pages where Docling produces no text (scanned pages
are handled by EasyOCR via Docling's built-in OCR pipeline).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

os.environ.setdefault("HF_HOME", r"D:\covenant\models\hf")
os.environ.setdefault("TRANSFORMERS_CACHE", r"D:\covenant\models\hf")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _bbox_from_prov(prov, page_w: float = 612.0, page_h: float = 792.0) -> dict:
    """Extract bbox from Docling provenance object."""
    try:
        b = prov.bbox
        return {
            "x0": float(b.l), "y0": float(b.t),
            "x1": float(b.r), "y1": float(b.b),
            "page_w": page_w, "page_h": page_h,
        }
    except Exception:
        return {"x0": 0.0, "y0": 0.0, "x1": page_w, "y1": page_h,
                "page_w": page_w, "page_h": page_h}


def _docling_available() -> bool:
    """Check if Docling should be used. Respects DOCLING_DISABLED env var."""
    import os
    if os.environ.get("DOCLING_DISABLED", "").lower() in ("1", "true", "yes"):
        return False
    # Try a safe import check — only check if onnxruntime is importable
    # (the actual crash comes from onnxruntime DLL in some environments)
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


_DOCLING_OK: bool | None = None


def parse_pdf_with_docling(
    pdf_path: Path,
    document_id: str,
    engagement_id: str,
) -> tuple[dict, list[dict]]:
    """Parse a PDF with Docling. Returns (parsed_doc_meta, chunks_list)."""
    global _DOCLING_OK
    if _DOCLING_OK is None:
        _DOCLING_OK = _docling_available()
    if not _DOCLING_OK:
        raise ImportError("Docling unavailable (onnxruntime DLL conflict or DOCLING_DISABLED=1)")

    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except Exception as e:
        raise ImportError(f"Docling import failed: {e}")

    pipeline_opts = PdfPipelineOptions()
    pipeline_opts.do_ocr = True          # enable OCR for scanned pages
    pipeline_opts.do_table_structure = True

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
        }
    )

    result = converter.convert(str(pdf_path))
    doc = result.document

    chunks: list[dict] = []
    articles: list[dict] = []
    tables_found: list[dict] = []
    warnings: list[dict] = []

    # Track section path as we walk the document
    current_section_path: list[str] = []
    chunk_seq = 0

    # Page dimensions (Docling exposes via pages)
    page_dims: dict[int, tuple[float, float]] = {}
    try:
        for page_no, page in doc.pages.items():
            if hasattr(page, 'size') and page.size:
                page_dims[page_no] = (float(page.size.width), float(page.size.height))
    except Exception:
        pass

    def get_page_dims(page_no: int) -> tuple[float, float]:
        return page_dims.get(page_no, (612.0, 792.0))

    for item, level in doc.iterate_items():
        item_type = type(item).__name__

        # Extract text
        try:
            text = item.text if hasattr(item, 'text') else str(item)
        except Exception:
            text = ""

        if not text or not text.strip():
            continue

        # Page number and bbox
        page_no = 1
        bbox = {"x0": 0.0, "y0": 0.0, "x1": 612.0, "y1": 792.0, "page_w": 612.0, "page_h": 792.0}
        try:
            if hasattr(item, 'prov') and item.prov:
                prov = item.prov[0] if isinstance(item.prov, list) else item.prov
                page_no = int(prov.page_no) if hasattr(prov, 'page_no') else 1
                pw, ph = get_page_dims(page_no)
                bbox = _bbox_from_prov(prov, pw, ph)
        except Exception:
            pass

        # Update section path for headings
        if item_type in ("SectionHeaderItem", "TextItem") and level <= 2:
            text_stripped = text.strip()
            # Detect article/section headings
            import re
            if re.match(r'^(ARTICLE|Article)\s+[IVXLCDM\d]+', text_stripped):
                current_section_path = [text_stripped]
                articles.append({"title": text_stripped, "page": page_no})
            elif re.match(r'^Section\s+\d+\.\d+', text_stripped):
                if len(current_section_path) >= 1:
                    current_section_path = [current_section_path[0], text_stripped]
                else:
                    current_section_path = [text_stripped]

        # Build section label display
        section_label = " > ".join(current_section_path) if current_section_path else f"Page {page_no}"

        chunk_id = f"{engagement_id}:{document_id}:struct:{chunk_seq:05d}"
        chunk_seq += 1

        chunks.append({
            "chunk_id": chunk_id,
            "document_id": document_id,
            "engagement_id": engagement_id,
            "page_number": page_no,
            "section_path": list(current_section_path),
            "section_label_display": section_label,
            "bbox": bbox,
            "text": text.strip(),
            "text_length_chars": len(text.strip()),
            "tokens_estimate": _estimate_tokens(text),
            "item_type": item_type,
            "tags": [],
        })

    # Detect tables
    try:
        for table in doc.tables:
            tables_found.append({
                "table_id": f"tbl_{len(tables_found)}",
                "page": getattr(table.prov[0], 'page_no', 1) if table.prov else 1,
            })
    except Exception:
        pass

    # Check for scanned pages (low text density)
    is_scanned = False
    try:
        total_pages = len(doc.pages) if doc.pages else 1
        text_pages = len({c["page_number"] for c in chunks if len(c["text"]) > 50})
        is_scanned = text_pages < (total_pages * 0.2)
    except Exception:
        pass

    parsed_meta = {
        "document_id": document_id,
        "engagement_id": engagement_id,
        "parser": "docling",
        "parser_version": "2.4.0",
        "page_count": len(doc.pages) if doc.pages else 0,
        "is_scanned": is_scanned,
        "chunks_produced": len(chunks),
        "tables_found": tables_found,
        "articles_found": articles,
        "warnings": warnings,
    }

    return parsed_meta, chunks


def parse_pdf_fallback(
    pdf_path: Path,
    document_id: str,
    engagement_id: str,
) -> tuple[dict, list[dict]]:
    """pdfplumber fallback when Docling is unavailable."""
    import pdfplumber

    chunks = []
    chunk_seq = 0
    page_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            chunk_id = f"{engagement_id}:{document_id}:struct:{chunk_seq:05d}"
            chunk_seq += 1
            chunks.append({
                "chunk_id": chunk_id,
                "document_id": document_id,
                "engagement_id": engagement_id,
                "page_number": i + 1,
                "section_path": [],
                "section_label_display": f"Page {i+1}",
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": float(page.width),
                         "y1": float(page.height), "page_w": float(page.width),
                         "page_h": float(page.height)},
                "text": text.strip(),
                "text_length_chars": len(text.strip()),
                "tokens_estimate": _estimate_tokens(text),
                "item_type": "TextItem",
                "tags": [],
            })

    return {
        "document_id": document_id,
        "engagement_id": engagement_id,
        "parser": "pdfplumber_fallback",
        "parser_version": "0.11.4",
        "page_count": page_count,
        "is_scanned": False,
        "chunks_produced": len(chunks),
        "tables_found": [],
        "articles_found": [],
        "warnings": [{"type": "docling_unavailable", "message": "Used pdfplumber fallback"}],
    }, chunks


def parse_pdf(
    pdf_path: Path,
    document_id: str,
    engagement_id: str,
) -> tuple[dict, list[dict]]:
    """Parse PDF with Docling, falling back to pdfplumber on error."""
    try:
        return parse_pdf_with_docling(pdf_path, document_id, engagement_id)
    except Exception as e:
        # Log the failure but don't silently swallow it
        import warnings
        warnings.warn(f"Docling failed for {pdf_path.name}: {e}. Using pdfplumber fallback.")
        return parse_pdf_fallback(pdf_path, document_id, engagement_id)
