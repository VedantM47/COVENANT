import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getEngagement, startPipeline, approveGate, uploadDocuments } from '../api/client'
import { STAGE_STATUS } from '../components/PdfViewer/colors'

const GATES = [
  { id: 'gate_1_rule_review', label: 'Rule Review' },
  { id: 'gate_2_mapping_review', label: 'Mapping Review' },
  { id: 'gate_3_exception_investigation', label: 'Exceptions' },
  { id: 'gate_4_senior', label: 'Senior Sign-off' },
  { id: 'gate_5_manager', label: 'Manager Sign-off' },
  { id: 'gate_6_partner', label: 'Partner Sign-off' },
]

export default function EngagementWorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [approverEmail, setApproverEmail] = useState('auditor@ey.com')
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null)

  const { data: eng, isLoading } = useQuery({
    queryKey: ['engagement', id],
    queryFn: () => getEngagement(id!),
    refetchInterval: 3000,
  })

  const startMutation = useMutation({
    mutationFn: () => startPipeline(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['engagement', id] }),
  })

  const approveMutation = useMutation({
    mutationFn: (gateId: string) =>
      approveGate(id!, gateId, { approver_email: approverEmail, notes: 'Auto-approved' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['engagement', id] }),
  })

  const uploadMutation = useMutation({
    mutationFn: () => uploadDocuments(id!, Array.from(uploadFiles!)),
    onSuccess: () => {
      setUploadFiles(null)
      qc.invalidateQueries({ queryKey: ['engagement', id] })
    },
  })

  if (isLoading || !eng) return <div className="p-6">Loading...</div>

  return (
    <div className="flex h-screen">
      {/* Left nav */}
      <aside className="w-56 border-r bg-gray-50 p-4 flex flex-col gap-2">
        <p className="font-bold text-sm truncate">{eng.borrower.name}</p>
        <p className="text-xs text-gray-500">{eng.test_date}</p>
        <hr className="my-2" />
        <Link to={`/engagements/${id}/documents`} className="text-sm hover:underline">Documents</Link>
        <Link to={`/engagements/${id}/audit`} className="text-sm hover:underline">Audit Trail</Link>
        <hr className="my-2" />
        <p className="text-xs font-semibold text-gray-500 uppercase">Gates</p>
        {GATES.map(g => (
          <div key={g.id} className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: eng.gates[g.id] === 'approved' ? STAGE_STATUS.completed : STAGE_STATUS.pending }}
            />
            <span className="text-xs">{g.label}</span>
          </div>
        ))}
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-xl font-bold">{eng.borrower.name} — {eng.engagement_code}</h1>
            <p className="text-sm text-gray-500">Status: {eng.status} · Pipeline: {eng.pipeline_stage}</p>
          </div>
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm"
          >
            {startMutation.isPending ? 'Starting...' : 'Start Pipeline'}
          </button>
        </div>

        {/* Document upload */}
        <section className="mb-6 border rounded-lg p-4">
          <h2 className="font-semibold mb-3">Upload Documents</h2>
          <div className="flex gap-3 items-center">
            <input
              type="file"
              multiple
              accept=".pdf,.xlsx,.csv,.json"
              onChange={e => setUploadFiles(e.target.files)}
              className="text-sm"
            />
            <button
              onClick={() => uploadMutation.mutate()}
              disabled={!uploadFiles || uploadMutation.isPending}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Upload
            </button>
          </div>
        </section>

        {/* Gate 1 approval — the round-trip test */}
        <section className="mb-6 border rounded-lg p-4">
          <h2 className="font-semibold mb-3">Gate 1 — Rule Review</h2>
          <div className="flex gap-3 items-center">
            <input
              className="border rounded px-2 py-1 text-sm"
              value={approverEmail}
              onChange={e => setApproverEmail(e.target.value)}
              placeholder="approver@ey.com"
            />
            <button
              onClick={() => approveMutation.mutate('gate_1_rule_review')}
              disabled={approveMutation.isPending}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              Approve Gate 1
            </button>
            <span className="text-sm text-gray-500">
              Status: {eng.gates['gate_1_rule_review'] ?? 'pending'}
            </span>
          </div>
        </section>

        {/* Gates overview */}
        <section className="border rounded-lg p-4">
          <h2 className="font-semibold mb-3">All Gates</h2>
          <div className="grid grid-cols-2 gap-3">
            {GATES.map(g => (
              <div key={g.id} className="flex items-center justify-between border rounded p-3">
                <span className="text-sm">{g.label}</span>
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: eng.gates[g.id] === 'approved'
                      ? STAGE_STATUS.completed
                      : STAGE_STATUS.pending,
                  }}
                >
                  {eng.gates[g.id] ?? 'pending'}
                </span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}
