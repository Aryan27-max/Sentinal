import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SERVICE_LABELS, clock } from '../lib/format'
import { useSentinel } from '../store/useSentinel'

interface Row {
  t: string
  rate: number | null
  base: number | null
  band: [number, number] | null
  anomalous: boolean
}

interface DotProps {
  cx?: number
  cy?: number
  payload?: Row
}

function AnomalyDot({ cx, cy, payload }: DotProps) {
  if (!payload?.anomalous || cx == null || cy == null) return null
  return <circle cx={cx} cy={cy} r={4.5} fill="var(--sev-high)" stroke="var(--surface)" strokeWidth={2} />
}

export function LiveChart() {
  const services = useSentinel((s) => s.services)
  const selected = useSentinel((s) => s.selected)
  const select = useSentinel((s) => s.select)
  const points = useSentinel((s) => s.history[selected])

  const data: Row[] = (points ?? []).map((p) => ({
    t: p.ts,
    rate: p.error_rate == null ? null : p.error_rate * 100,
    base: p.baseline_median == null ? null : p.baseline_median * 100,
    band: p.band_lo == null || p.band_hi == null ? null : [p.band_lo * 100, p.band_hi * 100],
    anomalous: p.anomalous,
  }))

  return (
    <section className="card min-w-0 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight">Error rate</h2>
          <p className="text-[13px] text-label-secondary">60 s sliding window, shaded band is the normal range</p>
        </div>
        <div
          className="flex overflow-x-auto rounded-[10px] bg-[color-mix(in_srgb,var(--label)_7%,transparent)] p-0.5"
          role="tablist"
        >
          {services.map((name) => (
            <button
              key={name}
              role="tab"
              aria-selected={selected === name}
              onClick={() => select(name)}
              className={`shrink-0 rounded-[8px] px-3 py-1 text-[13px] font-medium transition-colors ${
                selected === name
                  ? 'bg-surface text-label shadow-soft'
                  : 'text-label-secondary hover:text-label'
              }`}
            >
              {SERVICE_LABELS[name] ?? name}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 h-[260px] sm:h-[320px]">
        {data.length < 2 ? (
          <div className="grid h-full place-items-center text-[15px] text-label-secondary">
            Collecting data…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke="var(--hairline)" vertical={false} />
              <XAxis
                dataKey="t"
                tickFormatter={clock}
                tick={{ fill: 'var(--label-secondary)', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                tick={{ fill: 'var(--label-secondary)', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={44}
                domain={[0, (max: number) => Math.max(5, Math.ceil(max * 1.15))]}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--hairline)',
                  borderRadius: 12,
                  color: 'var(--label)',
                  fontSize: 12,
                }}
                labelFormatter={(t) => clock(String(t))}
                formatter={(value, name) => {
                  if (Array.isArray(value)) return [`${value.map((v) => Number(v).toFixed(1)).join('–')}%`, name]
                  return [`${Number(value).toFixed(2)}%`, name]
                }}
              />
              <Area
                dataKey="band"
                name="Normal range"
                stroke="none"
                fill="var(--accent)"
                fillOpacity={0.12}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                dataKey="base"
                name="Baseline"
                stroke="var(--label-secondary)"
                strokeDasharray="4 4"
                strokeWidth={1.25}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line
                dataKey="rate"
                name="Error rate"
                stroke="var(--accent)"
                strokeWidth={2.25}
                dot={<AnomalyDot />}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
