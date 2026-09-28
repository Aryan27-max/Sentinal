// Mirrors backend/app/models.py and the payloads built in backend/app/pipeline.py.

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface Alert {
  id: string
  ts: string
  service: string
  detector: 'error_rate' | 'latency' | 'silence'
  severity: Severity
  metric: string
  current: number
  baseline_median: number | null
  baseline_mad: number | null
  z: number | null
  window_seconds: number
  sample_lines: string[]
  message: string
}

export interface SeriesMetrics {
  volume: number
  silent: boolean
  anomalous: boolean
  error_rate: number | null
  baseline_median: number | null
  band: [number, number] | null
  z: number | null
  p95: number | null
  p95_baseline_median: number | null
  p95_band: [number, number] | null
  p95_anomalous: boolean
  warming_up: boolean
}

export interface Metrics {
  ts: string
  services: Record<string, SeriesMetrics>
  lines_per_sec: number
  warming_up: boolean
  chaos: Record<string, number> // scenario -> seconds remaining
}

export interface HistoryPoint {
  ts: string
  error_rate: number | null
  p95: number | null
  baseline_median: number | null
  band_lo: number | null
  band_hi: number | null
  anomalous: boolean
}

export interface Snapshot {
  services: string[]
  metrics: Metrics | null
  history: Record<string, HistoryPoint[]>
  alerts: Alert[]
  chaos: Record<string, number>
  warming_up: boolean
  config: Record<string, number>
}

export interface ChaosEvent {
  scenario: string
  active: boolean
  duration: number
  active_scenarios: Record<string, number>
}

export type WsMessage =
  | { type: 'snapshot'; data: Snapshot }
  | { type: 'metrics'; data: Metrics }
  | { type: 'alert'; data: Alert }
  | { type: 'chaos'; data: ChaosEvent }
  | { type: 'ping'; data: { ts: string } }
