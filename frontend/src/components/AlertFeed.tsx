import { clock, ms, pct } from '../lib/format'
import { useSentinel } from '../store/useSentinel'
import type { Alert, Severity } from '../types'

const SEVERITY_STYLE: Record<Severity, string> = {
  LOW: 'bg-sev-low',
  MEDIUM: 'bg-sev-medium',
  HIGH: 'bg-sev-high',
  CRITICAL: 'bg-sev-critical pulse',
}

function valueLine(a: Alert): string {
  if (a.detector === 'error_rate') return `${pct(a.current)} vs baseline ${pct(a.baseline_median)}`
  if (a.detector === 'latency') return `p95 ${ms(a.current)} vs baseline ${ms(a.baseline_median)}`
  return `No logs for ${Math.round(a.current)} s`
}

const DETECTOR_LABEL = { error_rate: 'Error rate', latency: 'Latency', silence: 'Silence' }

function AlertItem({ alert }: { alert: Alert }) {
  return (
    <li className="slide-in border-b border-hairline px-4 py-3.5 last:border-b-0 sm:px-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide text-white ${SEVERITY_STYLE[alert.severity]}`}
          >
            {alert.severity}
          </span>
          <span className="truncate text-[15px] font-semibold">{alert.service}</span>
        </div>
        <time className="shrink-0 text-[12px] text-label-secondary tabular-nums">{clock(alert.ts)}</time>
      </div>
      <div className="mt-1.5 text-[14px]">
        <span className="text-label-secondary">{DETECTOR_LABEL[alert.detector]} · </span>
        <span className="font-medium tabular-nums">{valueLine(alert)}</span>
        {alert.z != null && (
          <span className="text-label-secondary tabular-nums"> · z = {alert.z.toFixed(1)}</span>
        )}
      </div>
      {alert.sample_lines.length > 0 && (
        <pre className="mt-2 overflow-x-auto rounded-[10px] bg-[color-mix(in_srgb,var(--label)_5%,transparent)] px-2.5 py-2 font-mono text-[11px] leading-relaxed text-label-secondary">
          {alert.sample_lines.map((line) => line.replace(/^\S+\s/, '')).join('\n')}
        </pre>
      )}
    </li>
  )
}

export function AlertFeed() {
  const alerts = useSentinel((s) => s.alerts)
  return (
    <section className="card flex max-h-[640px] flex-col overflow-hidden">
      <div className="flex items-baseline justify-between px-4 pt-4 pb-3 sm:px-5">
        <h2 className="text-[17px] font-semibold tracking-tight">Alerts</h2>
        <span className="text-[13px] text-label-secondary tabular-nums">{alerts.length}</span>
      </div>
      {alerts.length === 0 ? (
        <p className="px-4 pb-6 text-[14px] text-label-secondary sm:px-5">
          No alerts yet. Alerts appear here the moment they fire.
        </p>
      ) : (
        <ul className="overflow-y-auto border-t border-hairline">
          {alerts.map((a) => (
            <AlertItem key={a.id} alert={a} />
          ))}
        </ul>
      )}
    </section>
  )
}
