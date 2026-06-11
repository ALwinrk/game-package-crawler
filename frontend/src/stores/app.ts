import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface SourceResult {
  source: string
  package: string
  version: string | null
  version_code: string | null
  version_name: string | null
  release_date: string | null
  file_size: string | null
  abis: string[]
  detail_url: string | null
  download_urls: string[]
  error: string | null
  app_name: string | null
  whats_new: string | null
}

export interface FetchResult {
  package: string
  name: string
  expected_version: string | null
  expected_version_code: string | null
  results: Record<string, SourceResult>
  best_version: string | null
  best_version_code: string | null
  compare_status: 'matched' | 'newer' | 'older' | 'not_found' | 'error'
  version_name_compare: string | null
  version_code_compare: string | null
  error: string | null
  app_name: string | null
  whats_new: string | null
}

export interface DownloadTask {
  id: string
  url: string
  package_name: string
  version: string
  arch: string
  save_path: string
  total_size: number
  downloaded_size: number
  status: string
  speed: string
  progress_pct: number
  error: string | null
}

export const useAppStore = defineStore('app', () => {
  // ── 主题 (v2.5) ──
  const darkMode = ref(false)

  function initDarkMode() {
    const saved = localStorage.getItem('darkMode')
    if (saved !== null) {
      darkMode.value = saved === 'true'
    } else {
      darkMode.value = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
    }
    applyDarkMode()
  }

  function toggleDark() {
    darkMode.value = !darkMode.value
    localStorage.setItem('darkMode', String(darkMode.value))
    applyDarkMode()
  }

  function applyDarkMode() {
    document.documentElement.classList.toggle('dark', darkMode.value)
  }

  // ── 状态 ──
  const activeTab = ref('daily')
  const loading = ref(false)
  const packageInput = ref('')
  const expectedVersion = ref('')
  const expectedVersionCode = ref('')
  const fetchMode = ref('fast') // fast | slow | all
  const results = ref<FetchResult[]>([])

  // 批量
  const batchTaskId = ref('')
  const batchProgress = ref(0)
  const batchTotal = ref(0)

  // 下载
  const downloadTasks = ref<DownloadTask[]>([])

  // 设置
  const apiBase = ref('http://127.0.0.1:8000')

  // ── 全局 WebSocket (替代轮询，v2.8+) ──
  let globalWs: WebSocket | null = null
  let wsReconnectTimer: any = null

  function connectGlobalWs() {
    if (globalWs && globalWs.readyState === WebSocket.OPEN) return
    try {
      const wsUrl = apiBase.value.replace('http', 'ws')
      globalWs = new WebSocket(`${wsUrl}/api/ws`)

      globalWs.onopen = () => {
        // 连接后立即刷新下载列表以获取当前状态
        refreshDownloads()
      }

      globalWs.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'download_progress') {
            const task = msg.data
            // 原地更新或添加下载任务
            const idx = downloadTasks.value.findIndex(t => t.id === task.id)
            if (idx >= 0) {
              downloadTasks.value[idx] = { ...downloadTasks.value[idx], ...task }
            } else {
              downloadTasks.value.push(task as DownloadTask)
            }
          } else if (msg.type === 'batch_fetch_progress') {
            // 批量查询进度 (来自 /api/fetch/batch)
            batchProgress.value = msg.data.progress_pct || 0
          }
        } catch { }
      }

      globalWs.onclose = () => {
        // 自动重连 (3s 延迟)
        wsReconnectTimer = setTimeout(connectGlobalWs, 3000)
      }
    } catch { }
  }

  // ── 计算 ──
  const latestResult = computed(() => results.value[0] || null)

  // ── 请求取消 (v3.8: 防止竞态条件导致结果串数据) ──
  let abortController: AbortController | null = null

  // ── API 调用 ──
  async function doFetch(packageName: string) {
    // 取消上一个未完成的请求，防止旧响应覆盖新结果
    if (abortController) {
      abortController.abort()
    }
    abortController = new AbortController()
    const signal = abortController.signal

    loading.value = true
    results.value = []
    try {
      const modePath = fetchMode.value === 'fast' ? '/api/fetch' : fetchMode.value === 'slow' ? '/api/fetch/slow' : '/api/fetch/all'
      const resp = await fetch(`${apiBase.value}${modePath}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          package: packageName,
          expected_version: expectedVersion.value || null,
          expected_version_code: expectedVersionCode.value || null,
          save_memo: true,
        }),
        signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      results.value = [data as FetchResult]
    } catch (e: any) {
      if (e.name === 'AbortError') return  // 被取消的请求静默忽略
      results.value = [{
        package: packageName,
        name: '',
        expected_version: null,
        expected_version_code: null,
        results: {},
        best_version: null,
        best_version_code: null,
        compare_status: 'error',
        error: e.message,
        version_name_compare: null,
        version_code_compare: null,
      }]
    } finally {
      loading.value = false
    }
  }

  // 批量查询多个包名
  async function doFetchBatch(packageNames: string[]) {
    // 取消上一个未完成的请求，防止旧响应覆盖新结果
    if (abortController) {
      abortController.abort()
    }
    abortController = new AbortController()
    const signal = abortController.signal

    loading.value = true
    results.value = []
    try {
      const resp = await fetch(`${apiBase.value}/api/fetch/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          packages: packageNames.map(p => ({
            package: p,
            expected_version: expectedVersion.value || null,
            expected_version_code: expectedVersionCode.value || null,
          })),
          mode: 'fast',
        }),
        signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      results.value = (data.results || []) as FetchResult[]
    } catch (e: any) {
      if (e.name === 'AbortError') return  // 被取消的请求静默忽略
      console.error('[batchFetch]', e)
      results.value = []
    } finally {
      loading.value = false
    }
  }

  // 检查记忆化
  async function checkMemo(packageName: string): Promise<{ version_code?: string; version_name?: string } | null> {
    try {
      const resp = await fetch(`${apiBase.value}/api/memo/${packageName}`)
      const data = await resp.json()
      if (data.found) return data.data
    } catch (e) { console.error('[checkMemo]', e) }
    return null
  }

  // 保存记忆
  async function saveMemo(pkg: string, vc: string | null, vn: string | null) {
    try {
      await fetch(`${apiBase.value}/api/memo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package: pkg, version_code: vc, version_name: vn }),
      })
    } catch (e) { console.error('[saveMemo]', e) }
  }

  // 提交下载
  async function submitDownload(url: string, pkg: string, version: string, arch: string, detailUrl: string = '') {
    try {
      await fetch(`${apiBase.value}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, package: pkg, version, arch, detail_url: detailUrl }),
      })
    } catch (e) { console.error('[submitDownload]', e) }
  }

  // 刷新下载列表
  async function refreshDownloads() {
    try {
      const resp = await fetch(`${apiBase.value}/api/download/tasks`)
      const data = await resp.json()
      downloadTasks.value = data.tasks || []
    } catch (e) { console.error('[refreshDownloads]', e) }
  }

  // 获取下载直链
  async function extractLinks(source: string, detailUrl: string, pkg: string, version: string = '') {
    try {
      const resp = await fetch(`${apiBase.value}/api/extract-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, detail_url: detailUrl, package: pkg, version }),
      })
      return await resp.json()
    } catch (e) {
      console.error('[extractLinks]', e)
      return null
    }
  }

  return {
    // 主题 (v2.5)
    darkMode, initDarkMode, toggleDark,
    // 业务
    activeTab, loading, packageInput, expectedVersion, expectedVersionCode,
    fetchMode, results, batchTaskId, batchProgress, batchTotal,
    downloadTasks, apiBase,
    latestResult,
    doFetch, doFetchBatch, checkMemo, saveMemo, submitDownload, refreshDownloads, extractLinks, connectGlobalWs,
  }
})
