<template>
  <div class="download-queue animate-fade-in-up">
    <el-card shadow="never" class="dl-card">
      <template #header>
        <div class="panel-header">
          <span class="panel-title">📥 下载队列</span>
          <el-button :icon="Refresh" size="small" @click="refresh" :loading="refreshing" round>
            刷新
          </el-button>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="!store.downloadTasks.length" class="empty-dl">
        <div class="empty-icon">📭</div>
        <p>暂无下载任务</p>
        <p class="empty-sub">去包名排查页面获取下载链接吧~</p>
      </div>

      <!-- 卡片化下载列表 -->
      <div v-else class="dl-cards stagger">
        <div
          v-for="task in store.downloadTasks"
          :key="task.id"
          class="dl-card-item"
          :class="`dl-status--${task.status}`"
        >
          <div class="dl-card-header">
            <span class="dl-pkg">{{ task.package_name }}</span>
            <el-tag :type="statusType(task.status)" size="small" effect="dark" round>
              {{ statusLabel(task.status) }}
            </el-tag>
          </div>
          <div class="dl-card-meta">
            <span>版本: <b>{{ task.version }}</b></span>
            <span>架构: <b>{{ task.arch || 'unknown' }}</b></span>
          </div>
          <el-progress
            :percentage="task.progress_pct"
            :status="task.status === 'completed' ? 'success' : task.status === 'error' ? 'exception' : undefined"
            :stroke-width="16"
            class="dl-progress"
          />
          <div class="dl-card-footer">
            <span v-if="task.status === 'downloading'" class="dl-speed">
              {{ formatSize(task.downloaded_size) }} / {{ formatSize(task.total_size) }}
              <span class="dl-speed-val">⚡ {{ task.speed || '...' }}</span>
            </span>
            <span v-else-if="task.status === 'completed'" class="dl-done">✅ 下载完成</span>
            <span v-else-if="task.error" class="dl-err">😵 {{ task.error }}</span>
            <div class="dl-actions">
              <el-button
                v-if="task.status === 'downloading'"
                size="small"
                type="warning"
                :icon="VideoPause"
                @click="pauseTask(task.id)"
                round
              >暂停</el-button>
              <el-button
                v-if="task.status === 'error' || task.status === 'cancelled'"
                size="small"
                type="danger"
                :icon="Delete"
                @click="cancelTask(task.id)"
                round
              >删除</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Refresh, VideoPause, Delete } from '@element-plus/icons-vue'
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
    pending: '⏳ 等待中', downloading: '📥 下载中', paused: '⏸️ 已暂停',
    completed: '✅ 已完成', error: '💥 失败', cancelled: '🚫 已取消',
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
.dl-card { border-radius: var(--radius-xl) !important; }

.panel-title { font-weight: 700; font-size: 15px; }
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 空状态 */
.empty-dl {
  text-align: center;
  padding: 48px 20px;
  color: var(--text-muted);
}
.empty-dl .empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-dl p { font-size: 15px; color: var(--text-secondary); }
.empty-sub { font-size: 13px !important; color: var(--text-muted) !important; }

/* 下载卡片 */
.dl-cards {
  display: grid;
  gap: 12px;
}

.dl-card-item {
  background: var(--bg-card);
  border: var(--border-card);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  transition: all var(--transition-base);
  animation: fadeInUp 0.35s ease both;
}
.dl-card-item:hover {
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}
.dl-status--downloading {
  border-left: 3px solid var(--color-primary-light);
}
.dl-status--completed {
  border-left: 3px solid var(--color-accent);
}
.dl-status--error {
  border-left: 3px solid #f56c6c;
}

.dl-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.dl-pkg {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.dl-card-meta {
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.dl-progress { margin-bottom: 10px; }
.dl-progress :deep(.el-progress-bar__outer) {
  border-radius: 8px !important;
}

.dl-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.dl-speed { color: var(--text-secondary); }
.dl-speed-val { color: var(--color-primary); font-weight: 600; margin-left: 6px; }
.dl-done { color: var(--color-accent); font-weight: 600; }
.dl-err { color: #f56c6c; max-width: 300px; overflow: hidden; text-overflow: ellipsis; }
.dl-actions { display: flex; gap: 6px; }
</style>
