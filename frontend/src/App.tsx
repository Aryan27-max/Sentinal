import { useEffect } from 'react'
import { AlertFeed } from './components/AlertFeed'
import { ChaosPanel } from './components/ChaosPanel'
import { LiveChart } from './components/LiveChart'
import { MetricCard } from './components/MetricCard'
import { NavBar } from './components/NavBar'
import { SERVICE_LABELS, ms, pct } from './lib/format'
import { connectSentinel } from './lib/ws'
import { activeSignals, useSentinel } from './store/useSentinel'

export default function App() {
  const handle = useSentinel((s) => s.handle)
  const setConnected = useSentinel((s) => s.setConnected)
  useEffect(() => connectSentinel(handle, setConnected), [handle, setConnected])

  const selected = useSentinel((s) => s.selected)
  const metrics = useSentinel((s) => s.metrics)
  const alertCount = useSentinel((s) => s.alerts.length)
  const active = activeSignals(metrics)
  const m = metrics?.services[selected]
  const scope = SERVICE_LABELS[selected] ?? selected
  const warming = metrics?.warming_up ?? true

  return (
    <>
      <NavBar />
      <main className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 py-5 sm:gap-5 sm:px-6 sm:py-8">
        {warming && (
          <div className="card flex items-center gap-3 px-4 py-3 text-[14px] sm:px-5">
            <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-accent" />
            <span>
              <span className="font-semibold">Learning baseline.</span>{' '}
              <span className="text-label-secondary">
                Sentinel watches normal traffic for about a minute before it raises alerts.
              </span>
            </span>
          </div>
        )}

        <ChaosPanel />

        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <MetricCard
            label={`Error rate · ${scope}`}
            value={pct(m?.error_rate)}
            detail={`Baseline ${pct(m?.baseline_median)}`}
            alert={m?.anomalous}
          />
          <MetricCard
            label={`p95 latency · ${scope}`}
            value={ms(m?.p95)}
            detail={`Baseline ${ms(m?.p95_baseline_median)}`}
            alert={m?.p95_anomalous}
          />
          <MetricCard
            label="Lines / sec"
            value={metrics ? metrics.lines_per_sec.toFixed(1) : '—'}
            detail={metrics?.services.all ? `${metrics.services.all.volume} in window` : undefined}
          />
          <MetricCard
            label="Active alerts"
            value={String(active)}
            detail={`${alertCount} raised this session`}
            alert={active > 0}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <LiveChart />
          <AlertFeed />
        </div>
      </main>
    </>
  )
}
