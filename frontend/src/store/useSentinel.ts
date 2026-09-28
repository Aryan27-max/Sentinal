import { create } from 'zustand'
import type { Alert, HistoryPoint, Metrics, WsMessage } from '../types'

const MAX_POINTS = 120
const MAX_ALERTS = 100

interface SentinelState {
  connected: boolean
  services: string[]
  selected: string
  metrics: Metrics | null
  history: Record<string, HistoryPoint[]>
  alerts: Alert[]
  chaosEndsAt: Record<string, number> // scenario -> epoch ms
  setConnected: (connected: boolean) => void
  select: (service: string) => void
  handle: (msg: WsMessage) => void
}

const endsAt = (remaining: Record<string, number>) =>
  Object.fromEntries(Object.entries(remaining).map(([k, s]) => [k, Date.now() + s * 1000]))

export const useSentinel = create<SentinelState>((set) => ({
  connected: false,
  services: ['all', 'api-gateway', 'auth-service', 'payment-service', 'inventory-service'],
  selected: 'all',
  metrics: null,
  history: {},
  alerts: [],
  chaosEndsAt: {},
  setConnected: (connected) => set({ connected }),
  select: (selected) => set({ selected }),
  handle: (msg) => {
    switch (msg.type) {
      case 'snapshot':
        set({
          services: msg.data.services,
          metrics: msg.data.metrics,
          history: msg.data.history,
          alerts: msg.data.alerts,
          chaosEndsAt: endsAt(msg.data.chaos),
        })
        break
      case 'metrics':
        set((state) => {
          const history = { ...state.history }
          for (const [name, m] of Object.entries(msg.data.services)) {
            const point: HistoryPoint = {
              ts: msg.data.ts,
              error_rate: m.error_rate,
              p95: m.p95,
              baseline_median: m.baseline_median,
              band_lo: m.band?.[0] ?? null,
              band_hi: m.band?.[1] ?? null,
              anomalous: m.anomalous,
            }
            history[name] = [...(history[name] ?? []), point].slice(-MAX_POINTS)
          }
          return { metrics: msg.data, history, chaosEndsAt: endsAt(msg.data.chaos) }
        })
        break
      case 'alert':
        set((state) => ({ alerts: [msg.data, ...state.alerts].slice(0, MAX_ALERTS) }))
        break
      case 'chaos':
        set({ chaosEndsAt: endsAt(msg.data.active_scenarios) })
        break
      case 'ping':
        break
    }
  },
}))

/** Signals currently out of their normal range, across services (the "all" series excluded). */
export function activeSignals(metrics: Metrics | null): number {
  if (!metrics) return 0
  return Object.entries(metrics.services)
    .filter(([name]) => name !== 'all')
    .reduce((n, [, m]) => n + Number(m.anomalous) + Number(m.p95_anomalous) + Number(m.silent), 0)
}
