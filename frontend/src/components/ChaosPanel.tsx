import { useEffect, useState } from 'react'
import { triggerChaos } from '../lib/api'
import { useSentinel } from '../store/useSentinel'

const SCENARIOS = [
  { id: 'db_outage', label: 'DB outage', hint: 'Payments errors to ~35%' },
  { id: 'latency_spike', label: 'Latency spike', hint: 'Gateway p95 to ~2 s' },
  { id: 'silence', label: 'Silence', hint: 'Inventory stops logging' },
]

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}

export function ChaosPanel() {
  const endsAt = useSentinel((s) => s.chaosEndsAt)
  const now = useNow(1000)
  const [error, setError] = useState<string | null>(null)

  const run = async (id: string) => {
    setError(null)
    try {
      await triggerChaos(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    }
  }

  const anyActive = Object.values(endsAt).some((t) => t > now)

  return (
    <section className="card p-4 sm:p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">Chaos Panel</h2>
          <p className="text-[13px] text-label-secondary">Inject a failure and watch Sentinel catch it</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {SCENARIOS.map((s) => {
            const remaining = Math.max(0, Math.ceil(((endsAt[s.id] ?? 0) - now) / 1000))
            const active = remaining > 0
            return (
              <button
                key={s.id}
                onClick={() => run(s.id)}
                title={s.hint}
                aria-pressed={active}
                className={`flex items-center gap-2 rounded-full border px-4 py-2 text-[14px] font-medium transition-colors ${
                  active
                    ? 'border-transparent bg-sev-high text-white'
                    : 'border-hairline bg-surface hover:bg-[color-mix(in_srgb,var(--label)_5%,var(--surface))]'
                }`}
              >
                {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />}
                {s.label}
                {active && <span className="tabular-nums opacity-80">{remaining}s</span>}
              </button>
            )
          })}
          <button
            onClick={() => run('recover')}
            disabled={!anyActive}
            className="rounded-full bg-accent px-4 py-2 text-[14px] font-medium text-white transition-opacity disabled:opacity-40"
          >
            Recover
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-[13px] text-sev-high">{error}</p>}
    </section>
  )
}
