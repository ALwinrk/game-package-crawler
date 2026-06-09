<template>
  <div class="daily-updates-panel">
    <el-card shadow="never" class="daily-card">
      <template #header>
        <div class="panel-header">
          <div class="header-left">
            <span class="panel-title">📰 实时更新游戏</span>
            <span v-if="lastFetchedAt" class="fetched-time">数据更新于 {{ lastFetchedAt }}</span>
          </div>
          <el-button size="small" :icon="Refresh" @click="refresh" :loading="loading" round>
            手动刷新
          </el-button>
        </div>
      </template>

      <el-tabs v-model="activeSource">
        <!-- APKPure -->
        <el-tab-pane label="APKPure" name="apkpure">
          <div v-if="data.apkpure.length" class="table-grid">
            <el-table v-for="(col, ci) in chunkItems(data.apkpure, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
              <el-table-column label="" width="40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <span class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" width="85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" width="95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
              <el-table-column label="" width="44" align="center">
                <template #default="{ row }">
                  <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="detail-link" title="打开详情页">🔗</a>
                  <span v-else class="no-icon">-</span>
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
                  <el-table-column label="" width="40">
                    <template #default="{ row }">
                      <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="36" shape="square" />
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div class="game-name-cell">
                        <span class="game-name">{{ row.app_name }}</span>
                        <span class="game-pkg">{{ row.package_name }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="下载" width="60" align="center">
                    <template #default="{ row }">
                      <span v-if="row.download_count" class="download-count">{{ row.download_count }}</span>
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="更新" width="95">
                    <template #default="{ row }">
                      <span class="update-time">{{ row.updated_at }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="" width="44" align="center">
                    <template #default="{ row }">
                      <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="detail-link" title="打开详情页">🔗</a>
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
            </el-tab-pane>
            <el-tab-pane label="🆕 最新更新" name="trending">
              <div v-if="(data as any).apkcombo_trending?.length" class="table-grid">
                <el-table v-for="(col, ci) in chunkItems((data as any).apkcombo_trending, 20)" :key="ci" :data="col" v-loading="loading" size="small" class="grid-table" empty-text="-">
                  <el-table-column label="" width="40">
                    <template #default="{ row }">
                      <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="36" shape="square" />
                      <span v-else class="no-icon">-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                    <template #default="{ row }">
                      <div class="game-name-cell">
                        <span class="game-name">{{ row.app_name }}</span>
                        <span class="game-pkg">{{ row.package_name }}</span>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column label="更新" width="95">
                    <template #default="{ row }">
                      <span class="update-time">{{ row.updated_at }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="" width="44" align="center">
                    <template #default="{ row }">
                      <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="detail-link" title="打开详情页">🔗</a>
                      <span v-else class="no-icon">-</span>
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
              <el-table-column label="" width="40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <span class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" width="85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" width="95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
              <el-table-column label="" width="44" align="center">
                <template #default="{ row }">
                  <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="detail-link" title="打开详情页">🔗</a>
                  <span v-else class="no-icon">-</span>
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
              <el-table-column label="" width="40">
                <template #default="{ row }">
                  <el-avatar v-if="row.icon_url" :src="row.icon_url" :size="36" shape="square" />
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="游戏名称" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="game-name-cell">
                    <span class="game-name">{{ row.app_name }}</span>
                    <span class="game-pkg">{{ row.package_name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="版本" width="85">
                <template #default="{ row }">
                  <span v-if="row.version_name" class="version-text">{{ row.version_name }}</span>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
              <el-table-column label="更新" width="95">
                <template #default="{ row }">
                  <span class="update-time">{{ row.updated_at }}</span>
                </template>
              </el-table-column>
              <el-table-column label="" width="44" align="center">
                <template #default="{ row }">
                  <a v-if="row.detail_url" :href="row.detail_url" target="_blank" class="detail-link" title="打开详情页">🔗</a>
                  <span v-else class="no-icon">-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-hint">暂无数据，等待后台抓取...</div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
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

const store = useAppStore()
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
    const json = await resp.json()
    data.value = json
    lastFetchedAt.value = json.last_fetched_at || ''
    const lm = resp.headers.get('Last-Modified')
    if (lm) lastModified = lm
    if (json.poll_interval) resetPollTimer(json.poll_interval * 1000)
  } catch (e) {
    console.error('Daily updates fetch failed', e)
  } finally {
    loading.value = false
  }
}

function resetPollTimer(ms: number): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(() => fetchUpdates(), ms)
}

function refresh(): void {
  fetchUpdates(true)
}

onMounted(async () => {
  await fetchUpdates()
  const intervalMs = (data.value.poll_interval || 300) * 1000
  pollTimer = window.setInterval(() => fetchUpdates(), intervalMs)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
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
.panel-title { font-weight: 700; font-size: 16px; }
.fetched-time { font-size: 12px; color: var(--text-muted); font-style: italic; }

.table-grid { display: flex; gap: 10px; overflow-x: auto; width: 100%; }
.grid-table { flex: 1; min-width: 0; font-size: 13px; }

.game-name-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.game-name { font-size: 13px; font-weight: 500; }
.game-pkg { font-size: 11px; color: var(--text-secondary); font-family: 'Consolas', 'Courier New', monospace; }

.version-text { font-size: 12px; color: var(--color-primary); font-weight: 500; }
.download-count { font-size: 12px; font-weight: 600; color: var(--color-primary); }
.update-time { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }

.detail-link { font-size: 15px; text-decoration: none; }
.detail-link:hover { transform: scale(1.2); }

.empty-hint { text-align: center; padding: 40px 0; color: var(--text-muted); font-size: 14px; }
.no-icon { color: var(--text-muted); font-size: 11px; }
</style>
