import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getAuditEvents } from '../api/client'

export default function AuditTrailPage() {
  const { id } = useParams<{ id: string }>()
  const [filter, setFilter] = useState('')

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['audit', id],
    queryFn: () => getAuditEvents(id!),
    refetchInterval: 5000,
  })

  const filtered = filter
    ? events.filter((e: Record<string, unknown>) =>
        String(e.event_type).toLowerCase().includes(filter.toLowerCase()) ||
        String(e.event_category).toLowerCase().includes(filter.toLowerCase())
      )
    : events

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-4">Audit Trail</h1>
      <div className="mb-4">
        <input
          className="border rounded px-3 py-2 w-64 text-sm"
          placeholder="Filter by event type..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <span className="ml-3 text-sm text-gray-500">{filtered.length} events</span>
      </div>
      {isLoading ? (
        <p>Loading...</p>
      ) : (
        <div className="space-y-1 font-mono text-xs">
          {filtered.map((ev: Record<string, unknown>, i: number) => (
            <div key={i} className="flex gap-3 border-b py-1">
              <span className="text-gray-400 w-48 flex-shrink-0">
                {String(ev.event_timestamp ?? '').slice(0, 19)}
              </span>
              <span className="font-semibold w-48 flex-shrink-0 text-blue-700">
                {String(ev.event_type)}
              </span>
              <span className="text-gray-600 truncate">
                {JSON.stringify(ev.payload_summary)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
