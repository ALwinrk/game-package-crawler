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
  error: string | null
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
  // ── 状态 ──
  const activeTab = ref('search')
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

  // ── 计算 ──
  const latestResult = computed(() => results.value[0] || null)

  const sourceStatus = computed(() => {
    if (!latestResult.value) return []
    return Object.entries(latestResult.value.results).map(([name, r]) => ({
      name,
      version: r.version,
      error: r.error,
      ok: r.version && !r.error,
      detail_url: r.detail_url,
    }))
  })

  // ── API 调用 ──
  async function doFetch(packageName: string) {
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
      })
      const data = await resp.json()
      results.value = [data as FetchResult]
    } catch (e: any) {
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
      }]
    } finally {
      loading.value = false
    }
  }

  // 批量查询多个包名
  async function doFetchBatch(packageNames: string[]) {
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
      })
      const data = await resp.json()
      results.value = (data.results || []) as FetchResult[]
    } catch (e: any) {
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
    } catch { }
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
    } catch { }
  }

  // 提交下载
  async function submitDownload(url: string, pkg: string, version: string, arch: string, detailUrl: string = '') {
    try {
      await fetch(`${apiBase.value}/api/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, package: pkg, version, arch, detail_url: detailUrl }),
      })
    } catch { }
  }

  // 刷新下载列表
  async function refreshDownloads() {
    try {
      const resp = await fetch(`${apiBase.value}/api/download/tasks`)
      const data = await resp.json()
      downloadTasks.value = data.tasks || []
    } catch { }
  }

  // 获取下载直链
  async function extractLinks(source: string, detailUrl: string, pkg: string) {
    try {
      const resp = await fetch(`${apiBase.value}/api/extract-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, detail_url: detailUrl, package: pkg }),
      })
      return await resp.json()
    } catch {
      return null
    }
  }

  return {
    activeTab, loading, packageInput, expectedVersion, expectedVersionCode,
    fetchMode, results, batchTaskId, batchProgress, batchTotal,
    downloadTasks, apiBase,
    latestResult, sourceStatus,
    doFetch, doFetchBatch, checkMemo, saveMemo, submitDownload, refreshDownloads, extractLinks,
  }
})
