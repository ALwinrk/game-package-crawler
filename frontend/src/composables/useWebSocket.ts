import { ref, onUnmounted } from 'vue'

export function useWebSocket(apiBase: string) {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const messages = ref<any[]>([])

  function connect(taskId?: string) {
    const wsUrl = apiBase.replace('http', 'ws')
    const url = taskId ? `${wsUrl}/api/ws/${taskId}` : `${wsUrl}/api/ws`

    ws.value = new WebSocket(url)
    ws.value.onopen = () => { connected.value = true }
    ws.value.onclose = () => { connected.value = false }
    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        messages.value.push(data)
      } catch { }
    }
  }

  function disconnect() {
    ws.value?.close()
    ws.value = null
  }

  onUnmounted(() => disconnect())

  return { ws, connected, messages, connect, disconnect }
}
