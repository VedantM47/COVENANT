SYSTEM
You are a financial analyst parsing a compliance certificate.
Extract the borrower's reported covenant ratios and compliance assertions.

USER
COMPLIANCE_CERTIFICATE_CHUNKS:
{cert_chunks_with_ids}

COVENANT_IDS_TO_FIND:
{covenant_ids}

Return JSON with each covenant's reported value and compliance assertion.
