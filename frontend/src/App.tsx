import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DashboardPage from './pages/DashboardPage'
import NewEngagementPage from './pages/NewEngagementPage'
import EngagementWorkspacePage from './pages/EngagementWorkspacePage'
import AuditTrailPage from './pages/AuditTrailPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10_000 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/engagements/new" element={<NewEngagementPage />} />
          <Route path="/engagements/:id" element={<EngagementWorkspacePage />} />
          <Route path="/engagements/:id/audit" element={<AuditTrailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
