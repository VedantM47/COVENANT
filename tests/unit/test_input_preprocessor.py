from app.stages.stage0_ingest.preprocessor import preprocess_document_chunks


def test_preprocess_document_chunks_removes_noise_and_duplicates():
    chunks = [
        {
            "chunk_id": "chunk_00001",
            "page_number": 1,
            "section_path": ["Article 7"],
            "section_label_display": "Article 7",
            "text": "Credit Agreement\nCredit Agreement\n\nSection 7.10\nBorrower shall not exceed 5.00x leverage ratio.\n",
        },
        {
            "chunk_id": "chunk_00002",
            "page_number": 1,
            "section_path": ["Article 7"],
            "section_label_display": "Article 7",
            "text": "Page 1 of 3\n\nCredit Agreement\nCredit Agreement\nSection 7.10\nBorrower shall not exceed 5.00x leverage ratio.\n",
        },
        {
            "chunk_id": "chunk_00003",
            "page_number": 2,
            "section_path": ["Article 7"],
            "section_label_display": "Article 7",
            "text": "\n\nThe Borrower shall maintain EBITDA of at least $95,000,000 as of December 31, 2024.\n",
        },
    ]

    cleaned = preprocess_document_chunks(chunks, document_type="credit_agreement")

    assert len(cleaned) == 2
    assert "Credit Agreement" not in cleaned[0]["text"]
    assert "Page 1 of 3" not in cleaned[0]["text"]
    assert "Borrower shall not exceed 5.00x leverage ratio." in cleaned[0]["text"]
    assert "$95,000,000" in cleaned[1]["text"]
    assert "December 31, 2024" in cleaned[1]["text"]
    assert cleaned[0]["text"] == cleaned[0]["text"].strip()


def test_preprocess_document_chunks_preserves_numeric_and_date_values():
    chunks = [
        {
            "chunk_id": "chunk_00001",
            "page_number": 1,
            "section_label_display": "Schedule",
            "text": "Threshold Schedule\nThreshold Schedule\nEffective Date: 2024-01-01\n5.00:1.00\n",
        },
        {
            "chunk_id": "chunk_00002",
            "page_number": 1,
            "section_label_display": "Schedule",
            "text": "Threshold Schedule\nThreshold Schedule\nEffective Date: 2024-01-01\n5.00:1.00\n",
        },
    ]

    cleaned = preprocess_document_chunks(chunks, document_type="amendment_letter")

    assert len(cleaned) == 1
    assert "2024-01-01" in cleaned[0]["text"]
    assert "5.00:1.00" in cleaned[0]["text"]
    assert cleaned[0]["deduplication_reason"] == "duplicate_content"


def test_preprocess_document_chunks_preserves_short_audit_terms():
    chunks = [
        {
            "chunk_id": "chunk_00001",
            "text": "EBITDA\n\nBorrower shall maintain minimum EBITDA.",
        },
    ]

    cleaned = preprocess_document_chunks(chunks, document_type="credit_agreement")

    assert len(cleaned) == 1
    assert "EBITDA" in cleaned[0]["text"]


def test_preprocess_document_chunks_tracks_non_adjacent_duplicates():
    chunks = [
        {"chunk_id": "chunk_00001", "text": "Borrower shall maintain EBITDA of at least $95,000,000."},
        {"chunk_id": "chunk_00002", "text": "Borrower shall not exceed 5.00x leverage ratio."},
        {"chunk_id": "chunk_00003", "text": "Borrower shall maintain EBITDA of at least $95,000,000."},
    ]

    cleaned = preprocess_document_chunks(chunks, document_type="credit_agreement")

    assert len(cleaned) == 2
    assert cleaned[0]["deduplication_reason"] == "duplicate_content"
    assert cleaned[0]["duplicate_chunk_ids"] == ["chunk_00003"]
    assert "deduplication_reason" not in cleaned[1]
