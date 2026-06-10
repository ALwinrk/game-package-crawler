<template>
  <div class="daily-updates-panel" :class="{ fw: fullWidth }">
    <el-card shadow="never" class="daily-card">
      <template #header>
        <div class="panel-header">
          <div class="header-left">
            <span class="panel-title">📰 实时更新游戏</span>
            <span v-if="lastFetchedAt" class="fetched-time">数据更新于 {{ lastFetchedAt }}</span>
          </div>
          <div class="header-actions">
            <!-- v3.6: 数据源选择器 -->
            <el-popover placement="bottom" :width="200" trigger="click">
              <template #reference>
                <el-button size="small" round>
                  📡 数据源 ({{ selectedSources.length }}/5)
                </el-button>
              </template>
              <div class="source-selector">
                <div class="source-actions">
                  <el-button size="small" text @click="selectAllSources">全选</el-button>
                  <el-button size="small" text @click="clearSources">清空</el-button>
                </div>
                <el-checkbox-group v-model="selectedSources">
                  <el-checkbox v-for="s in allSources" :key="s.value" :label="s.value" class="source-checkbox">
                    {{ s.label }}
                  </el-checkbox>
                </el-checkbox-group>
              </div>
            </el-popover>
            <el-button size="small" @click="refreshPanel" :loading="loadingPanel" :disabled="!selectedSources.length" round>
              🔄 刷新面板
            </el-button>
            <el-button size="small" :icon="Refresh" @click="refreshIncremental"
              :loading="loadingIncr" :disabled="!selectedSources.length" round>
              增量刷新
            </el-button>
            <el-button size="small" type="primary" :icon="Refresh" @click="refreshFull"
              :loading="loadingFull" :disabled="!selectedSources.length" round>
              全量刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeSource">
        <!-- APKPure -->
        <el-tab-pane label="APKPure" name="apkpure">
          <div v-if="data.apkpure.length" class="table-grid">
            <el-table v-for="(col, ci) in chunkItems(data.apkpure, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
              <el-table-column label="" :width="fullWidth ? 52 : 40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="fullWidth ? 48 : 36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="game-name-link">{{ row.app_name }}</a>
                        <span v-else class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg" @contextmenu.prevent="onContextMenu($event, row.package_name)">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" :width="fullWidth ? 95 : 85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" :width="fullWidth ? 105 : 95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
        </el-tab-pane>

        <!-- APKCombo -->
        <el-tab-pane label="APKCombo" name="apkcombo">
          <el-tabs v-model="comboTab" type="card" size="small">
            <el-tab-pane label="🔥 热门" name="popular">
              <div v-if="data.apkcombo.length" class="table-grid">
                <el-table v-for="(col, ci) in chunkItems(data.apkcombo, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
                  <el-table-column label="" :width="fullWidth ? 52 : 40">
                    <template #default="{ row }">
                      <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="fullWidth ? 48 : 36" shape="square" />
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div class="game-name-cell">
                        <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="game-name-link">{{ row.app_name }}</a>
                        <span v-else class="game-name">{{ row.app_name }}</span>
                        <span class="game-pkg" @contextmenu.prevent="onContextMenu($event, row.package_name)">{{ row.package_name }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="更新" :width="fullWidth ? 105 : 95">
                    <template #default="{ row }">
                      <span class="update-time">{{ row.updated_at }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
            </el-tab-pane>
            <el-tab-pane label="🆕 最新更新" name="trending">
              <div v-if="data.apkcombo_trending.length" class="table-grid">
                <el-table v-for="(col, ci) in chunkItems(data.apkcombo_trending, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
                  <el-table-column label="" :width="fullWidth ? 52 : 40">
                    <template #default="{ row }">
                      <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="fullWidth ? 48 : 36" shape="square" />
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div class="game-name-cell">
                        <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="game-name-link">{{ row.app_name }}</a>
                        <span v-else class="game-name">{{ row.app_name }}</span>
                        <span class="game-pkg" @contextmenu.prevent="onContextMenu($event, row.package_name)">{{ row.package_name }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="更新" :width="fullWidth ? 105 : 95">
                    <template #default="{ row }">
                      <span class="update-time">{{ row.updated_at }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- APKVision 最近更新 -->
        <el-tab-pane label="APKVision 最近更新" name="apkvision_updated">
          <div v-if="data.apkvision_updated.length" class="table-grid">
            <el-table v-for="(col, ci) in chunkItems(data.apkvision_updated, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
              <el-table-column label="" :width="fullWidth ? 52 : 40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="fullWidth ? 48 : 36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="game-name-link">{{ row.app_name }}</a>
                        <span v-else class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg" @contextmenu.prevent="onContextMenu($event, row.package_name)">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" :width="fullWidth ? 95 : 85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" :width="fullWidth ? 105 : 95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
        </el-tab-pane>

        <!-- APKVision 新游戏 -->
        <el-tab-pane label="APKVision 新游戏" name="apkvision_new">
          <div v-if="data.apkvision_new.length" class="table-grid">
            <el-table v-for="(col, ci) in chunkItems(data.apkvision_new, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
              <el-table-column label="" :width="fullWidth ? 52 : 40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="fullWidth ? 48 : 36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="game-name-link">{{ row.app_name }}</a>
                        <span v-else class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg" @contextmenu.prevent="onContextMenu($event, row.package_name)">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" :width="fullWidth ? 95 : 85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" :width="fullWidth ? 105 : 95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 右键复制菜单 -->
    <div v-if="ctxMenu.show" class="ctx-menu" :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }" @mouseleave="hideMenu">
      <div class="ctx-menu-item" @click="copyPkg">📋 复制包名</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app'

interface GameItem {
  app_name: string
  icon_url: string
  detail_url: string
  package_name: string
  download_count: string
  version_name: string
  updated_at: string
}

interface DailyData {
  apkpure: GameItem[]
  apkcombo: GameItem[]
  apkcombo_trending: GameItem[]
  apkvision_updated: GameItem[]
  apkvision_new: GameItem[]
  poll_interval: number
  last_fetched_at?: string
}

const props = defineProps<{ fullWidth?: boolean }>()
const store = useAppStore()

// v3.6: 数据源选择
const allSources = [
  { value: 'apkpure', label: 'APKPure' },
  { value: 'apkcombo', label: 'APKCombo 热门' },
  { value: 'apkcombo_trending', label: 'APKCombo 最新更新' },
  { value: 'apkvision_updated', label: 'APKVision 最近更新' },
  { value: 'apkvision_new', label: 'APKVision 新游戏' },
]
const STORAGE_KEY = 'daily_sources'
const savedSources = localStorage.getItem(STORAGE_KEY)
const selectedSources = ref<string[]>(
  savedSources ? JSON.parse(savedSources) : allSources.map(s => s.value)
)

function persistSources() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedSources.value))
}

function selectAllSources() {
  selectedSources.value = allSources.map(s => s.value)
  persistSources()
}

function clearSources() {
  selectedSources.value = []
  persistSources()
}
const data = ref<DailyData>({
  apkpure: [], apkcombo: [], apkcombo_trending: [],
  apkvision_updated: [], apkvision_new: [],
  poll_interval: 300
})
const loading = ref(false)
const activeSource = ref('apkpure')
const comboTab = ref('popular')
const lastFetchedAt = ref('')
let pollTimer: number | null = null
let lastModified: string | null = null

// 右键复制菜单
const ctxMenu = reactive({ show: false, x: 0, y: 0, pkg: '' })
function onContextMenu(e: MouseEvent, pkg: string) {
  ctxMenu.show = true
  let mx = e.clientX + 4
  let my = e.clientY + 4
  // 防止溢出屏幕 (菜单 min-width: 140px + padding)
  if (mx + 160 > window.innerWidth) mx = e.clientX - 160
  if (my + 40 > window.innerHeight) my = e.clientY - 40
  ctxMenu.x = mx
  ctxMenu.y = my
  ctxMenu.pkg = pkg
}
function copyPkg() {
  navigator.clipboard.writeText(ctxMenu.pkg).then(() => {
    ElMessage.success({ message: `已复制 ${ctxMenu.pkg}`, duration: 1500 })
  }).catch(() => {
    ElMessage.error('复制失败')
  })
  ctxMenu.show = false
}
function hideMenu() { ctxMenu.show = false }

function chunkItems(items: GameItem[], size: number): GameItem[][] {
  const chunks: GameItem[][] = []
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size))
  }
  return chunks
}

async function fetchUpdates(force: boolean = false): Promise<void> {
  loading.value = true
  try {
    const headers: Record<string, string> = {}
    if (!force && lastModified) headers['If-Modified-Since'] = lastModified
    const resp = await fetch(`${store.apiBase}/api/daily-updates?limit=60`, { headers })
    if (resp.status === 304) return
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const json = await resp.json()
    data.value = json
    lastFetchedAt.value = json.last_fetched_at || ''
    const lm = resp.headers.get('Last-Modified')
    if (lm) lastModified = lm
    if (json.poll_interval) resetPollTimer(json.poll_interval * 1000)
  } catch (e) {
    console.error('Daily updates fetch failed', e)
    ElMessage.error('面板数据加载失败，请检查网络连接')
  } finally {
    loading.value = false
  }
}

function resetPollTimer(ms: number): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(() => fetchUpdates(), ms)
}

const loadingIncr = ref(false)
const loadingFull = ref(false)
const loadingPanel = ref(false)

/** 刷新面板 — 仅从数据库拉取最新数据, 不触发爬取 */
async function refreshPanel(): Promise<void> {
  if (!selectedSources.value.length) {
    ElMessage.warning('请先选择数据源')
    return
  }
  loadingPanel.value = true
  try {
    await fetchUpdates(true)
    ElMessage.success('面板已刷新')
  } catch {
    ElMessage.warning('面板数据加载失败')
  } finally {
    loadingPanel.value = false
  }
}

const refreshPolling = ref(false)  // v3.5: 后台刷新轮询中

/** v3.5: 后台刷新完成后轮询拉取数据 */
function startRefreshPolling(label: string): void {
  if (refreshPolling.value) return
  refreshPolling.value = true
  let attempts = 0
  const maxAttempts = 24
  const timer = setInterval(async () => {
    attempts++
    await fetchUpdates(true)
    try {
      const sr = await fetch(`${store.apiBase}/api/daily-updates/refresh-status`)
      const sj = await sr.json()
      if (!sj.running || attempts >= maxAttempts) {
        clearInterval(timer)
        refreshPolling.value = false
        if (attempts >= maxAttempts) ElMessage.warning(`${label}：等待超时，请稍后手动刷新面板`)
        else ElMessage.success(`${label}完成`)
      }
    } catch {
      clearInterval(timer)
      refreshPolling.value = false
    }
  }, 5000)
}

/** v3.6 fire-and-forget: 增量刷新 — 立即返回, 后台执行, 支持选择源 */
async function refreshIncremental(): Promise<void> {
  if (!selectedSources.value.length) {
    ElMessage.warning('请先选择数据源')
    return
  }
  loadingIncr.value = true
  persistSources()
  try {
    const resp = await fetch(`${store.apiBase}/api/daily-updates/refresh-incremental`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sources: selectedSources.value }),
    })
    const result = await resp.json()
    if (result.status === 'started') {
      ElMessage.info('增量刷新已启动，后台抓取中...')
      startRefreshPolling('增量刷新')
    } else if (result.status === 'busy') {
      ElMessage.warning('刷新已在后台运行中')
    } else {
      ElMessage.warning(result.message || '未知状态')
    }
  } catch {
    ElMessage.error('增量刷新请求失败')
  } finally {
    loadingIncr.value = false
  }
}

/** v3.6 fire-and-forget: 全量刷新 — 立即返回, 后台执行, 支持选择源 */
async function refreshFull(): Promise<void> {
  if (!selectedSources.value.length) {
    ElMessage.warning('请先选择数据源')
    return
  }
  loadingFull.value = true
  persistSources()
  try {
    const resp = await fetch(`${store.apiBase}/api/daily-updates/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sources: selectedSources.value }),
    })
    const result = await resp.json()
    if (result.status === 'started') {
      ElMessage.info('全量刷新已启动，后台抓取中...')
      startRefreshPolling('全量刷新')
    } else if (result.status === 'busy') {
      ElMessage.warning('刷新已在后台运行中')
    } else {
      ElMessage.warning(result.message || '未知状态')
    }
  } catch {
    ElMessage.error('全量刷新请求失败')
  } finally {
    loadingFull.value = false
  }
}

// 兼容旧调用
async function refresh(): Promise<void> {
  await refreshFull()
}

onMounted(async () => {
  await fetchUpdates()
  const intervalMs = (data.value.poll_interval || 300) * 1000
  pollTimer = window.setInterval(() => fetchUpdates(), intervalMs)
  document.addEventListener('click', hideMenu)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('click', hideMenu)
})
</script>

<style scoped>
.daily-card { border-radius: var(--radius-xl) !important; width: 100%; }

.panel-header {
  display: flex; justify-content: space-between; align-items: center;
}
.header-left {
  display: flex; align-items: center; gap: 14px;
}
.header-actions {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.source-selector { display: flex; flex-direction: column; gap: 4px; }
.source-actions { display: flex; gap: 8px; margin-bottom: 4px; }
.source-checkbox { margin: 4px 0; }
.panel-title { font-weight: 700; font-size: 17px; }
.fetched-time { font-size: 13px; color: var(--text-muted); font-style: italic; }
.header-actions .el-button { font-size: 13px; }

.table-grid { display: flex; gap: 10px; overflow-x: auto; width: 100%; }
.grid-table { flex: 1; min-width: 0; font-size: 13px; }

.game-name-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.game-name { font-size: 13px; font-weight: 500; }
.game-name-link { font-size: 13px; font-weight: 500; color: var(--el-text-color-primary, #303133); text-decoration: none; }
.game-name-link:hover { color: var(--el-color-primary, #409eff); text-decoration: underline; }
.game-pkg { font-size: 11px; color: var(--text-secondary); font-family: 'Consolas', 'Courier New', monospace; }

.version-text { font-size: 12px; color: var(--color-primary); font-weight: 500; }
.download-count { font-size: 12px; font-weight: 600; color: var(--color-primary); }
.update-time { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }

/* v3.6: full-width 模式 — 字段自适应放大 */
.fw .game-name, .fw .game-name-link { font-size: 15px; }
.fw .game-pkg { font-size: 13px; }
.fw .version-text, .fw .update-time { font-size: 13px; }
.fw .el-avatar { --el-avatar-size: 48px !important; }


.empty-hint { text-align: center; padding: 40px 0; color: var(--text-muted); font-size: 14px; }
.no-icon { color: var(--text-muted); font-size: 11px; }

.game-pkg { cursor: context-menu; }

.ctx-menu {
  position: fixed; z-index: 9999;
  background: var(--el-bg-color-overlay, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 8px; padding: 4px 0;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  min-width: 140px;
}
.ctx-menu-item {
  padding: 8px 16px; cursor: pointer;
  font-size: 13px; white-space: nowrap;
  color: var(--el-text-color-regular, #333);
}
.ctx-menu-item:hover {
  background: var(--el-color-primary-light-9, #ecf5ff);
  color: var(--el-color-primary, #409eff);
}
</style>
