import { activeSignals, useSentinel } from '../store/useSentinel'

export function NavBar() {
  const connected = useSentinel((s) => s.connected)
  const warming = useSentinel((s) => s.metrics?.warming_up ?? true)
  const active = useSentinel((s) => activeSignals(s.metrics))

  let label = 'All systems normal'
  let tone = 'bg-[#30D158]'
  if (!connected) {
    label = 'Reconnecting'
    tone = 'bg-label-secondary'
  } else if (active > 0) {
    label = `${active} active alert${active === 1 ? '' : 's'}`
    tone = 'bg-sev-high'
  } else if (warming) {
    label = 'Learning baseline'
    tone = 'bg-accent'
  }

  return (
    <header className="glass sticky top-0 z-20 border-b border-hairline">
      <div className="mx-auto flex h-14 max-w-[1240px] items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
            <rect width="32" height="32" rx="8" fill="var(--accent)" />
            <path
              d="M6 17h5l2.5-6 4 12 2.5-6H26"
              fill="none"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-[17px] font-semibold tracking-tight">Sentinel</span>
        </div>
        <div
          className="flex items-center gap-2 rounded-full border border-hairline bg-surface px-3 py-1.5 text-[13px] font-medium shadow-soft"
          role="status"
          aria-live="polite"
        >
          <span className="relative flex h-2 w-2">
            {(active > 0 || (warming && connected)) && (
              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${tone}`} />
            )}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${tone}`} />
          </span>
          {label}
        </div>
      </div>
    </header>
  )
}
