export const SERVICE_LABELS: Record<string, string> = {
  all: 'All',
  'api-gateway': 'Gateway',
  'auth-service': 'Auth',
  'payment-service': 'Payments',
  'inventory-service': 'Inventory',
}

export const pct = (x: number | null | undefined, digits = 1) =>
  x == null ? '—' : `${(x * 100).toFixed(digits)}%`

export const ms = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x)} ms`)

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
