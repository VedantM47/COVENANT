import { create } from 'zustand'
import type { EngagementResponse } from '../types/api'

interface EngagementStore {
  engagements: EngagementResponse[]
  current: EngagementResponse | null
  setEngagements: (list: EngagementResponse[]) => void
  setCurrent: (eng: EngagementResponse | null) => void
  updateGate: (engId: string, gateId: string, status: string) => void
}

export const useEngagementStore = create<EngagementStore>((set) => ({
  engagements: [],
  current: null,
  setEngagements: (list) => set({ engagements: list }),
  setCurrent: (eng) => set({ current: eng }),
  updateGate: (engId, gateId, status) =>
    set((state) => ({
      engagements: state.engagements.map((e) =>
        e.engagement_id === engId
          ? { ...e, gates: { ...e.gates, [gateId]: status } }
          : e
      ),
      current:
        state.current?.engagement_id === engId
          ? { ...state.current, gates: { ...state.current.gates, [gateId]: status } }
          : state.current,
    })),
}))
