# pipeline_inputs — Final Input Files
## Cross-referenced against POC_INPUTS.md (7 inputs) and AUDITOR_INPUT_SPEC.md

Run `python generate_all_inputs.py` to regenerate sample_inputs if needed.

---

## INPUT 1 — Credit Agreement PDF
**Pipeline layer:** Layer 1+2 (LLM reads covenant rules)
**Purpose:** PDF of the loan contract — system extracts covenant formulas, EBITDA definitions, thresholds

| File | Size | Status |
|------|------|--------|
| `ABL_50M_Facility_Credit_Agreement_First_Lien.pdf` | 2490.8 KB | REQUIRED |
| `Full_Credit_Agreement_6x_Total_Leverage_Ratio.pdf` | 4505.3 KB | REQUIRED |
| `Howmet_Aerospace_Amendment4_Credit_Agreement.pdf` | 402.6 KB | REQUIRED |
| `Industrial_Company_Full_Credit_Agreement_EBITDA_Addbacks.pdf` | 1360.7 KB | REQUIRED |
| `Investment_Grade_Credit_Agreement_Compliance_Certificate.pdf` | 1414.9 KB | REQUIRED |

## INPUT 2 — Amendment Letters
**Pipeline layer:** Layer 1+2 (threshold overrides)
**Purpose:** Side letters modifying original thresholds — must reconcile with base agreement

| File | Size | Status |
|------|------|--------|
| `Full_Credit_Agreement_6x_HTM.htm` | 2156.1 KB | AVAILABLE |
| `Howmet_Amendment4_Credit_Agreement.htm` | 183.3 KB | AVAILABLE |

## INPUT 3 — Trial Balance
**Pipeline layer:** Layer 3 (account mapping + numbers)
**Purpose:** Borrower raw financials — system NLP-maps accounts to formula components

| File | Size | Status |
|------|------|--------|
| `trial_balance_firstbank_q4_2024.xlsx` | 23.6 KB | REQUIRED |
| `trial_balance_firstbank_q4_2024_simple.csv` | 0.7 KB | REQUIRED |

## INPUT 4 — Compliance Certificate
**Pipeline layer:** Layer 5 (assertion being tested)
**Purpose:** CFO-signed assertion — system compares vs independently computed ratios

| File | Size | Status |
|------|------|--------|
| `compliance_cert_firstbank_q4_2024.json` | 2.0 KB | REQUIRED |
| `compliance_certificate_firstbank_q4_2024.pdf` | 53.6 KB | REQUIRED |

## INPUT 5 — Regulatory Filings (XBRL/FDIC)
**Pipeline layer:** Layer 5 Round 2 (cross-verify)
**Purpose:** Independent regulatory data — cross-verify borrower numbers (skip Round 1)

| File | Size | Status |
|------|------|--------|
| `FDIC_JPMorgan_Q4_2024_Financials.json` | 1.6 KB | AVAILABLE |
| `XBRL_BankOfAmerica_CompanyFacts_SEC.json` | 6551.0 KB | AVAILABLE |
| `XBRL_GoldmanSachs_CompanyFacts_SEC.json` | 5548.2 KB | AVAILABLE |
| `XBRL_JPMorgan_Chase_CompanyFacts_SEC.json` | 7375.6 KB | AVAILABLE |
| `XBRL_WellsFargo_CompanyFacts_SEC.json` | 7511.2 KB | AVAILABLE |

## INPUT 6 — LTM Quarterly Financials
**Pipeline layer:** Layer 3+4 Round 2 (LTM reconstruction)
**Purpose:** 4 quarters for trailing 12-month EBITDA — single period fine for Round 1

| File | Size | Status |
|------|------|--------|
| `ltm_quarterly_firstbank_2024.csv` | 1.0 KB | AVAILABLE |

## INPUT 7 — Engagement Metadata
**Pipeline layer:** Layer 6 (evidence pack header)
**Purpose:** Engagement ID, lender, borrower, auditor, file paths

| File | Size | Status |
|------|------|--------|
| `engagement_metadata.json` | 0.9 KB | AVAILABLE |

---

## Cross-Reference: POC_INPUTS.md vs Files Present

| Input # | Description | Files in Folder | Round |
|---------|-------------|-----------------|-------|
| 1 | Credit Agreement PDF | 5 real PDFs | Round 1 — use Full_Credit_Agreement_6x |
| 2 | Amendment Letters | 2 HTM files | Round 1 — Howmet is Amendment 4 |
| 3 | Trial Balance | 1 XLSX + 1 CSV | Round 1 — use XLSX |
| 4 | Compliance Certificate | 1 PDF + 1 JSON | Round 1 — PDF for demo, JSON for pipeline |
| 5 | Regulatory XBRL / FDIC | 5 JSON files | Round 2 — skip for Round 1 |
| 6 | LTM Quarterly Financials | 1 CSV | Round 2 — single period ok for Round 1 |
| 7 | Engagement Metadata | 1 JSON | Round 1 |

**Total: 18 files | 38 MB 671 KB**

---

## Round 1 Minimum (4 files to run full pipeline + evidence pack)

```
INPUT_1_credit_agreement/Full_Credit_Agreement_6x_Total_Leverage_Ratio.pdf
INPUT_3_trial_balance/trial_balance_firstbank_q4_2024.xlsx
INPUT_4_compliance_certificate/compliance_certificate_firstbank_q4_2024.pdf
INPUT_7_engagement_metadata/engagement_metadata.json
```

## Baked-in Exceptions (what the pipeline should catch)

| ID | Type | Borrower Value | Correct Value | Impact |
|----|------|---------------|---------------|--------|
| ERR-001 | Circular restructuring cap misapplied | EBITDA $131,025,000 | EBITDA $136,444,444 | +$5,419,444 |
| ERR-002 | Junior Sub Notes excluded (no consent) | Net Debt $147,500,000 | Net Debt $187,500,000 | +$40,000,000 |
| — | Net Leverage Ratio variance | 4.228x (borrower) | 1.374x (correct) | 2.854x gap |