<template>
  <div class="download-queue">
    <el-card shadow="never">
      <template #header>
        <div class="panel-header">
          <span>下载队列</span>
          <el-button :icon="Refresh" size="small" @click="refresh" :loading="refreshing">
            刷新
          </el-button>
        </div>
      </template>

      <el-empty v-if="!store.downloadTasks.length" description="暂无下载任务" />

      <el-table v-else :data="store.downloadTasks" stripe size="small">
        <el-table-column prop="package_name" label="包名" width="200" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="arch" label="架构" width="100" />
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress_pct"
              :status="row.status === 'completed' ? 'success' : row.status === 'error' ? 'exception' : undefined"
              :text-inside="true"
              :stroke-width="20"
            />
            <div class="progress-detail" v-if="row.status === 'downloading'">
              {{ formatSize(row.downloaded_size) }} / {{ formatSize(row.total_size) }}
              @ {{ row.speed || '...' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'downloading'"
              size="small" type="warning"
              @click="pauseTask(row.id)"
            >暂停</el-button>
            <el-button
              v-if="row.status === 'error' || row.status === 'cancelled'"
              size="small" type="danger"
              @click="cancelTask(row.id)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const refreshing = ref(false)
let timer: any = null

async function refresh() {
  refreshing.value = true
  await store.refreshDownloads()
  refreshing.value = false
}

function pauseTask(id: string) {
  fetch(`${store.apiBase}/api/download/${id}/pause`, { method: 'POST' })
}

function cancelTask(id: string) {
  fetch(`${store.apiBase}/api/download/${id}/cancel`, { method: 'POST' })
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '等待中', downloading: '下载中', paused: '已暂停',
    completed: '已完成', error: '失败', cancelled: '已取消',
  }
  return map[s] || s
}

function statusType(s: string): string {
  const map: Record<string, string> = {
    pending: 'info', downloading: 'warning', paused: 'info',
    completed: 'success', error: 'danger', cancelled: 'info',
  }
  return map[s] || 'info'
}

function formatSize(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(1)} ${units[i]}`
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.panel-header { display: flex; justify-content: space-between; align-items: center; }
.progress-detail { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
