// Exact spec from CODING_AGENT_BRIEF.md section 9

export const HIGHLIGHT_COLORS = {
  COVENANT_BODY:      { bg: '#FFF4B8', border: '#E5C100', style: 'tint' },
  DEFINED_TERM:       { bg: null,      border: '#336CC1', style: 'underline' },
  THRESHOLD:          { bg: '#FFE3E0', border: '#E8392C', style: 'rounded_box' },
  FORMULA_COMPONENT:  { bg: null,      border: '#2DB757', style: 'underline' },
  CAP_VALUE:          { bg: '#FFF1DC', border: '#F5A623', style: 'box' },
  CROSS_REF_SECTION:  { bg: null,      border: '#9B5DE5', style: 'underline' },
  AMENDMENT_DELETION: { bg: null,      border: '#E8392C', style: 'strikethrough' },
  AMENDMENT_ADDITION: { bg: null,      border: '#2DB757', style: 'underline_bold' },
} as const

export const CONFIDENCE_BANDS = {
  high:   { dot: '#2DB757', border_pulse: false, threshold: 0.90 },
  medium: { dot: '#F5A623', border_pulse: false, threshold: 0.70 },
  low:    { dot: '#E8392C', border_pulse: true,  threshold: 0.00 },
} as const

export const STAGE_STATUS = {
  pending:       '#C4C4CD',
  running:       '#FFE600',
  awaiting_gate: '#9B5DE5',
  completed:     '#2DB757',
  failed:        '#E8392C',
} as const

export type HighlightType = keyof typeof HIGHLIGHT_COLORS
export type ConfidenceBand = keyof typeof CONFIDENCE_BANDS
