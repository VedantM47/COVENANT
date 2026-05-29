// Mirror of app/schemas/api.py

export interface BorrowerInfo {
  name: string
  cik?: string
  rssd_id?: string
  fdic_cert?: string
}

export interface LenderInfo {
  name: string
}

export interface AuditTeamMember {
  role: string
  email: string
  name: string
}

export interface CreateEngagementRequest {
  engagement_code: string
  borrower: BorrowerInfo
  lender: LenderInfo
  loan_id?: string
  test_date: string
  audit_team?: AuditTeamMember[]
  external_egress_enabled?: boolean
  llm_provider_override?: string
}

export interface EngagementResponse {
  engagement_id: string
  engagement_code: string
  borrower: BorrowerInfo
  lender: LenderInfo
  loan_id: string
  test_date: string
  status: string
  pipeline_stage: string
  audit_team: AuditTeamMember[]
  external_egress_enabled: boolean
  llm_provider: string
  created_at: string
  gates: Record<string, string>
}

export interface CovenantRatioResult {
  covenant_id: string
  covenant_name: string
  ratio_exact_rational: string
  ratio_float: number
  ratio_display: string
  threshold_value: number
  threshold_operator: string
  is_compliant: boolean
  z3_cross_check: string
  trace: Record<string, unknown>[]
}

export interface Exception_ {
  exception_id: string
  covenant_id: string
  type: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  kind: string
  description: string
  conclusion?: string
}

export interface GateApproveRequest {
  item_ids?: string[]
  approver_email: string
  notes?: string
}

export interface GateSignOffRequest {
  signer_email: string
  confirmations: string[]
}

export interface HighlightPayload {
  document_id: string
  page_number: number
  bbox: { x0: number; y0: number; x1: number; y1: number; page_w: number; page_h: number }
  highlight_type: string
  confidence_band: string
  extracted_value_display: string
  tooltip_text: string
}
