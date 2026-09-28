interface Props {
  label: string
  value: string
  detail?: string
  alert?: boolean
}

export function MetricCard({ label, value, detail, alert }: Props) {
  return (
    <div className="card p-4 sm:p-5">
      <div className="text-[13px] font-medium text-label-secondary">{label}</div>
      <div
        className={`mt-1 text-[28px] leading-tight font-semibold tracking-tight tabular-nums sm:text-[34px] ${
          alert ? 'text-sev-high' : ''
        }`}
      >
        {value}
      </div>
      {detail && <div className="mt-1 truncate text-[13px] text-label-secondary">{detail}</div>}
    </div>
  )
}
