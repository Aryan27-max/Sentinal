import type { WsMessage } from '../types'

const MIN_DELAY_MS = 500
const MAX_DELAY_MS = 10_000

/** Connects to /ws and reconnects with exponential backoff. Returns a function that closes it. */
export function connectSentinel(
  onMessage: (msg: WsMessage) => void,
  onStatus: (connected: boolean) => void,
): () => void {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
  let socket: WebSocket | null = null
  let delay = MIN_DELAY_MS
  let timer: number | undefined
  let closed = false

  const open = () => {
    socket = new WebSocket(url)
    socket.onopen = () => {
      delay = MIN_DELAY_MS
      onStatus(true)
    }
    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data) as WsMessage)
      } catch {
        // ignore malformed frames
      }
    }
    socket.onclose = () => {
      onStatus(false)
      if (closed) return
      timer = window.setTimeout(open, delay)
      delay = Math.min(delay * 2, MAX_DELAY_MS)
    }
    socket.onerror = () => socket?.close()
  }

  open()
  return () => {
    closed = true
    window.clearTimeout(timer)
    socket?.close()
  }
}
