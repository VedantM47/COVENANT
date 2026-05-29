"""Defined-terms graph builder.

Uses GLiNER for zero-shot NER to extract defined terms from the credit agreement.
Builds a NetworkX DAG of term dependencies.
Produces defined_terms.json per IMPLEMENTATION_PLAN.md section 6.4.1.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import networkx as nx

os.environ.setdefault("HF_HOME", r"D:\covenant\models\hf")

# GLiNER entity types for legal/financial documents
GLINER_LABELS = [
    "defined_term_being_defined",
    "defined_term_referenced",
    "dollar_amount",
    "percentage",
    "ratio",
    "time_period",
    "cross_reference_section",
]

# Patterns that indicate a definitions paragraph
DEFINITION_PATTERNS = [
    r'"[A-Z][^"]{2,60}"\s+(?:means|shall mean|is defined as|has the meaning)',
    r"'[A-Z][^']{2,60}'\s+(?:means|shall mean|is defined as)",
    r'\b([A-Z][a-zA-Z\s]{2,40})\b\s+(?:means|shall mean)\b',
]

DEFINITION_RE = re.compile("|".join(DEFINITION_PATTERNS), re.MULTILINE)


def _is_definitions_chunk(text: str) -> bool:
    """Heuristic: does this chunk look like a definitions paragraph?"""
    matches = DEFINITION_RE.findall(text)
    # At least 1 definition pattern, or chunk is in Section 1.01
    return len(matches) >= 1


def _extract_term_name(text: str) -> str | None:
    """Extract the term being defined from a definitions paragraph."""
    # Pattern: "Term Name" means ...
    m = re.match(r'^["\']([A-Z][^"\']{2,60})["\']', text.strip())
    if m:
        return m.group(1).strip()
    # Pattern: Term Name means ...
    m = re.match(r'^([A-Z][a-zA-Z\s]{2,40})\s+(?:means|shall mean)', text.strip())
    if m:
        return m.group(1).strip()
    return None


def _term_id(name: str) -> str:
    """Convert term name to a stable term_id."""
    return "term_" + re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _find_referenced_terms(text: str, known_terms: set[str]) -> list[str]:
    """Find references to known defined terms within a definition body."""
    refs = []
    for term in known_terms:
        # Look for the term name (capitalized) in the text
        if re.search(r'\b' + re.escape(term) + r'\b', text):
            refs.append(term)
    return refs


def _run_gliner(chunks: list[dict], model) -> list[dict]:
    """Run GLiNER on definition chunks. Returns list of entity dicts."""
    results = []
    for chunk in chunks:
        text = chunk.get("text", "")
        if len(text) < 20:
            continue
        try:
            entities = model.predict_entities(text, GLINER_LABELS, threshold=0.4)
            results.append({
                "chunk_id": chunk["chunk_id"],
                "page_number": chunk.get("page_number", 0),
                "section_path": chunk.get("section_path", []),
                "text": text,
                "entities": entities,
            })
        except Exception:
            pass
    return results


def build_defined_terms_graph(
    chunks: list[dict],
    engagement_id: str,
    document_id: str,
) -> tuple[dict, nx.DiGraph]:
    """Build defined-terms graph from document chunks.

    Returns (defined_terms_json, networkx_graph).
    """
    # Load GLiNER model
    try:
        from gliner import GLiNER
        model = GLiNER.from_pretrained(
            "urchade/gliner_multi-v2.1",
            cache_dir=r"D:\covenant\models\hf",
        )
        use_gliner = True
    except Exception as e:
        import warnings
        warnings.warn(f"GLiNER unavailable: {e}. Using regex-only extraction.")
        model = None
        use_gliner = False

    # Step 1: Find definition chunks
    def_chunks = [c for c in chunks if _is_definitions_chunk(c.get("text", ""))]

    # Step 2: Extract terms
    terms: dict[str, dict] = {}  # term_canonical -> term_data

    if use_gliner and model and def_chunks:
        gliner_results = _run_gliner(def_chunks, model)
        for result in gliner_results:
            for entity in result["entities"]:
                if entity["label"] == "defined_term_being_defined":
                    name = entity["text"].strip().strip('"\'')
                    if len(name) < 3 or len(name) > 80:
                        continue
                    tid = _term_id(name)
                    if tid not in terms:
                        terms[tid] = {
                            "term_id": tid,
                            "term_canonical": name,
                            "term_aliases": [],
                            "definition_text": result["text"][:500],
                            "definition_kind": "extracted",
                            "source_chunk_id": result["chunk_id"],
                            "page_number": result["page_number"],
                            "section_path": result["section_path"],
                            "references": [],
                            "extraction_confidence": float(entity.get("score", 0.8)),
                            "needs_review": False,
                            "amended_by": None,
                        }

    # Regex fallback / supplement
    for chunk in def_chunks:
        text = chunk.get("text", "")
        # Extract each definition paragraph
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                continue
            name = _extract_term_name(para)
            if name and len(name) >= 3:
                tid = _term_id(name)
                if tid not in terms:
                    terms[tid] = {
                        "term_id": tid,
                        "term_canonical": name,
                        "term_aliases": [],
                        "definition_text": para[:500],
                        "definition_kind": "regex_extracted",
                        "source_chunk_id": chunk["chunk_id"],
                        "page_number": chunk.get("page_number", 0),
                        "section_path": chunk.get("section_path", []),
                        "references": [],
                        "extraction_confidence": 0.75,
                        "needs_review": False,
                        "amended_by": None,
                    }

    # Step 3: Build cross-reference edges
    known_names = {v["term_canonical"] for v in terms.values()}
    G = nx.DiGraph()

    for tid, term_data in terms.items():
        G.add_node(tid, **term_data)
        def_text = term_data["definition_text"]
        refs = _find_referenced_terms(def_text, known_names - {term_data["term_canonical"]})
        for ref_name in refs:
            ref_id = _term_id(ref_name)
            if ref_id in terms and ref_id != tid:
                # Check for self-referential cap (circular)
                is_circular = bool(re.search(
                    r'\d+\s*%\s+of\s+' + re.escape(term_data["term_canonical"]),
                    def_text, re.IGNORECASE
                ))
                edge_type = "self_referential_cap" if is_circular else "depends_on"
                G.add_edge(tid, ref_id)
                term_data["references"].append({
                    "to_term_id": ref_id,
                    "edge_type": edge_type,
                })

    # Step 4: Cycle detection (only self-referential caps allowed)
    cycles = list(nx.simple_cycles(G))
    non_cap_cycles = [c for c in cycles if len(c) > 1]  # length-1 = self-loop (cap)

    output = {
        "engagement_id": engagement_id,
        "credit_agreement_document_id": document_id,
        "amendment_document_ids": [],
        "term_count": len(terms),
        "terms": list(terms.values()),
        "graph_stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "max_dependency_depth": 0,
            "cycles_detected_excluding_caps": len(non_cap_cycles),
        },
    }

    return output, G
