export async function triggerChaos(scenario: string): Promise<void> {
  const res = await fetch(`/api/chaos/${scenario}`, { method: 'POST' })
  if (!res.ok) throw new Error(`Chaos ${scenario} failed (${res.status})`)
}
