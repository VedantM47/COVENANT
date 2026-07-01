import axios from 'axios'
import type {
  CreateEngagementRequest, EngagementResponse,
  GateApproveRequest, GateSignOffRequest,
} from '../types/api'
import { demoAuditEvents, demoEngagements, getDemoEngagement } from '../demoData'

const api = axios.create({ baseURL: '/api/v1' })

// Engagements
export const createEngagement = (req: CreateEngagementRequest) =>
  api.post<EngagementResponse>('/engagements', req).then(r => r.data)

export const getEngagement = (id: string) =>
  getDemoEngagement(id) ??
  api.get<EngagementResponse>(`/engagements/${id}`).then(r => r.data)

export const listEngagements = () =>
  api.get<EngagementResponse[]>('/engagements')
    .then(r => (r.data.length > 0 ? r.data : demoEngagements))
    .catch(() => demoEngagements)

// Pipeline
export const startPipeline = (id: string) =>
  api.post(`/engagements/${id}/pipeline/start`).then(r => r.data)

export const getPipelineStatus = (id: string) =>
  api.get(`/engagements/${id}/pipeline/status`).then(r => r.data)

// Gates
export const getGate = (id: string, gateId: string) =>
  api.get(`/engagements/${id}/gates/${gateId}`).then(r => r.data)

export const approveGate = (id: string, gateId: string, req: GateApproveRequest) =>
  api.post(`/engagements/${id}/gates/${gateId}/approve`, req).then(r => r.data)

export const signOffGate = (id: string, gateId: string, req: GateSignOffRequest) =>
  api.post(`/engagements/${id}/gates/${gateId}/sign-off`, req).then(r => r.data)

// Audit
export const getAuditEvents = (id: string) =>
  getDemoEngagement(id)
    ? Promise.resolve(demoAuditEvents)
    : api.get(`/engagements/${id}/audit/events`).then(r => r.data)

export const verifyChain = (id: string) =>
  api.post(`/engagements/${id}/audit/verify`).then(r => r.data)

// Seal
export const sealEngagement = (id: string) =>
  api.post(`/engagements/${id}/seal`).then(r => r.data)

// Documents
export const uploadDocuments = (id: string, files: File[]) => {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  return api.post(`/engagements/${id}/documents`, form).then(r => r.data)
}

export const listDocuments = (id: string) =>
  api.get(`/engagements/${id}/documents`).then(r => r.data)
