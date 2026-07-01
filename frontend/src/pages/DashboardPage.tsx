import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listEngagements } from '../api/client'
import { STAGE_STATUS } from '../components/PdfViewer/colors'
import { isDemoEngagement } from '../demoData'

const STATUS_LABELS: Record<string, string> = {
  created: 'Created',
  running: 'Running',
  awaiting_gate: 'Awaiting Gate',
  completed: 'Completed',
  failed: 'Failed',
}

export default function DashboardPage() {
  const { data: engagements = [], isLoading } = useQuery({
    queryKey: ['engagements'],
    queryFn: listEngagements,
    refetchInterval: 5000,
  })

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Covenant Compliance Platform</h1>
        <Link
          to="/engagements/new"
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          + New Engagement
        </Link>
      </div>

      {isLoading ? (
        <p className="text-gray-500">Loading...</p>
      ) : engagements.length === 0 ? (
        <p className="text-gray-500">No engagements yet. Create one to get started.</p>
      ) : (
        <div className="space-y-3">
          {engagements.map((eng) => (
            <Link
              key={eng.engagement_id}
              to={`/engagements/${eng.engagement_id}`}
              className="block border rounded-lg p-4 hover:bg-gray-50 transition"
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">{eng.borrower.name}</p>
                    {isDemoEngagement(eng.engagement_id) && (
                      <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-800">
                        Demo
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500">{eng.engagement_code} · Test date: {eng.test_date}</p>
                </div>
                <span
                  className="text-xs px-2 py-1 rounded-full font-medium"
                  style={{
                    backgroundColor: STAGE_STATUS[eng.status as keyof typeof STAGE_STATUS] ?? '#C4C4CD',
                    color: '#000',
                  }}
                >
                  {STATUS_LABELS[eng.status] ?? eng.status}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
