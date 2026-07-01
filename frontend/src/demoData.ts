import type { EngagementResponse } from './types/api'

export const DEMO_ENGAGEMENT_ID = 'DEMO-FIRSTBANK-Q4-2024'

export const demoEngagements: EngagementResponse[] = [
  {
    engagement_id: DEMO_ENGAGEMENT_ID,
    engagement_code: 'ENG-DEMO-2024-Q4',
    borrower: {
      name: 'FirstBank Holdings LLC',
      cik: '0000000000',
      fdic_cert: 'DEMO-4421',
    },
    lender: {
      name: 'LendCo Private Credit Fund II LP',
    },
    loan_id: 'TLB-DEMO-001',
    test_date: '2024-12-31',
    status: 'awaiting_gate',
    pipeline_stage: 'stage_1_extract',
    audit_team: [
      {
        role: 'Associate',
        email: 'auditor@ey.com',
        name: 'Audit Associate',
      },
      {
        role: 'Manager',
        email: 'manager@ey.com',
        name: 'Audit Manager',
      },
    ],
    external_egress_enabled: true,
    llm_provider: 'mock',
    created_at: '2026-07-01T12:00:00Z',
    gates: {
      gate_1_rule_review: 'pending',
      gate_2_mapping_review: 'pending',
      gate_3_exception_investigation: 'pending',
      gate_4_senior: 'pending',
      gate_5_manager: 'pending',
      gate_6_partner: 'pending',
    },
  },
]

export const demoAuditEvents = [
  {
    event_timestamp: '2026-07-01T12:00:00Z',
    event_type: 'ENGAGEMENT_CREATED',
    event_category: 'workflow',
    payload_summary: {
      engagement_code: 'ENG-DEMO-2024-Q4',
      borrower: 'FirstBank Holdings LLC',
    },
  },
  {
    event_timestamp: '2026-07-01T12:01:18Z',
    event_type: 'DOCUMENT_UPLOADED',
    event_category: 'ingest',
    payload_summary: {
      document_id: 'DOC-DEMO-CA',
      filename: 'credit_agreement_firstbank.pdf',
      doc_type: 'credit_agreement',
    },
  },
  {
    event_timestamp: '2026-07-01T12:02:04Z',
    event_type: 'CHUNKS_PRODUCED',
    event_category: 'ingest',
    payload_summary: {
      document_id: 'DOC-DEMO-CA',
      raw_chunk_count: 148,
      chunk_count: 92,
    },
  },
  {
    event_timestamp: '2026-07-01T12:03:22Z',
    event_type: 'COVENANT_CLAUSE_CLASSIFIED',
    event_category: 'extraction',
    payload_summary: {
      candidates_found: 3,
      method: 'deberta_zero_shot',
    },
  },
  {
    event_timestamp: '2026-07-01T12:04:11Z',
    event_type: 'LLM_CALL_MADE',
    event_category: 'extraction',
    payload_summary: {
      provider: 'mock',
      model: 'fixture-replay',
      source_verification_failures: 0,
    },
  },
]

export const getDemoEngagement = (id: string) =>
  demoEngagements.find((engagement) => engagement.engagement_id === id)

export const isDemoEngagement = (id?: string) =>
  Boolean(id && getDemoEngagement(id))
