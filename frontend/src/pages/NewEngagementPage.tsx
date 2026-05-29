import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { createEngagement } from '../api/client'
import type { CreateEngagementRequest } from '../types/api'

export default function NewEngagementPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState<Partial<CreateEngagementRequest>>({
    engagement_code: '',
    borrower: { name: '' },
    lender: { name: '' },
    test_date: new Date().toISOString().split('T')[0],
    external_egress_enabled: true,
    audit_team: [],
  })

  const mutation = useMutation({
    mutationFn: createEngagement,
    onSuccess: (data) => navigate(`/engagements/${data.engagement_id}`),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate(form as CreateEngagementRequest)
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Create New Engagement</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Engagement Code</label>
          <input
            className="w-full border rounded px-3 py-2"
            value={form.engagement_code}
            onChange={e => setForm(f => ({ ...f, engagement_code: e.target.value }))}
            placeholder="ENG-2025-EY-001"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Borrower Name</label>
          <input
            className="w-full border rounded px-3 py-2"
            value={form.borrower?.name}
            onChange={e => setForm(f => ({ ...f, borrower: { ...f.borrower!, name: e.target.value } }))}
            placeholder="FirstBank Corp"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Lender Name</label>
          <input
            className="w-full border rounded px-3 py-2"
            value={form.lender?.name}
            onChange={e => setForm(f => ({ ...f, lender: { ...f.lender!, name: e.target.value } }))}
            placeholder="LendCo Private Credit Fund II LP"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Test Date</label>
          <input
            type="date"
            className="w-full border rounded px-3 py-2"
            value={form.test_date}
            onChange={e => setForm(f => ({ ...f, test_date: e.target.value }))}
            required
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="egress"
            checked={form.external_egress_enabled}
            onChange={e => setForm(f => ({ ...f, external_egress_enabled: e.target.checked }))}
          />
          <label htmlFor="egress" className="text-sm">Enable external data egress (FFIEC, EDGAR, FDIC)</label>
        </div>
        {mutation.isError && (
          <p className="text-red-600 text-sm">Error creating engagement. Please try again.</p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="px-4 py-2 border rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {mutation.isPending ? 'Creating...' : 'Create Engagement'}
          </button>
        </div>
      </form>
    </div>
  )
}
