<template>
  <div class="batch-panel animate-fade-in-up">
    <el-card shadow="never" class="batch-card">
      <template #header>
        <div class="panel-header">
          <span class="panel-title">📦 批量 Excel 排查</span>
          <span class="tip">支持 .xlsx / .xls，自动检测 package_name 列 — 拖拽即可，懒人福音 😎</span>
        </div>
      </template>

      <!-- 上传区 -->
      <el-upload
        ref="uploadRef"
        :action="`${store.apiBase}/api/batch/upload`"
        :on-success="onUploadSuccess"
        :on-error="onUploadError"
        :auto-upload="true"
        accept=".xlsx,.xls"
        drag
        class="batch-upload"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">
          拖拽 Excel 到此处 或 <em>点击上传</em>
        </div>
        <div class="upload-sub">列格式: package_name | expected_version_code(可选) | expected_version_name(可选)</div>
      </el-upload>

      <!-- 进度 -->
      <div v-if="store.batchTaskId" class="batch-progress animate-fade-in-up">
        <el-divider />
        <div class="task-info">
          <span class="task-id">任务: {{ store.batchTaskId }}</span>
          <el-tag :type="batchStatusType" effect="dark" round>{{ batchStatusLabel }}</el-tag>
          <span class="task-progress-text">{{ store.batchProgress.toFixed(1) }}%</span>
        </div>
        <el-progress
          :percentage="store.batchProgress"
          :status="store.batchProgress >= 100 ? 'success' : undefined"
          :text-inside="false"
          :stroke-width="18"
          class="batch-bar"
        />
        <div class="task-actions">
          <el-button size="small" :icon="VideoPause" @click="pauseBatch" :disabled="batchStatus !== 'running'" round>
            暂停
          </el-button>
          <el-button size="small" :icon="VideoPlay" @click="resumeBatch" :disabled="batchStatus !== 'paused'" round>
            继续
          </el-button>
          <el-button size="small" type="danger" :icon="Close" @click="cancelBatch" :disabled="batchStatus === 'completed'" round>
            取消
          </el-button>
          <el-button
            v-if="batchStatus === 'completed'"
            size="small"
            type="success"
            :icon="Download"
            @click="downloadResult"
            round
          >
            下载结果 Excel
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { UploadFilled, VideoPause, VideoPlay, Close, Download } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useAppStore()

const batchStatus = ref('')
const uploadRef = ref()
const batchSummary = ref<any>(null)

const batchStatusLabel = computed(() => {
  const map: Record<string, string> = {
    running: '🏃 运行中', paused: '⏸️ 已暂停', completed: '✅ 完成',
    cancelled: '🚫 已取消', error: '💥 出错',
  }
  return map[batchStatus.value] || batchStatus.value
})

function onUploadSuccess(resp: any) {
  store.batchTaskId = resp.task_id
  store.batchTotal = resp.total
  batchStatus.value = 'running'
  batchSummary.value = null
  ElMessage.success({ message: `📦 批量任务已启动: ${resp.filename} (${resp.total} 行)`, customClass: 'cyber-msg' })

  const wsUrl = store.apiBase.replace('http', 'ws')
  const ws = new WebSocket(`${wsUrl}/api/ws/${resp.task_id}`)
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'batch_progress') {
        store.batchProgress = data.data.progress_pct || 0
        batchStatus.value = data.data.status
        if (data.data.status === 'completed') {
          batchSummary.value = data.data.summary || {}
          showCompletionDialog()
          ws.close()
        }
      }
    } catch { }
  }
}

function showCompletionDialog() {
  const s = batchSummary.value
  if (!s) return
  ElMessageBox.alert(
    `<div style="line-height:2.2;font-size:14px;">
      <p style="font-size:17px;font-weight:700;margin-bottom:8px;">🎉 排查完成！共 <b>${store.batchTotal}</b> 个包名</p>
      <p>✅ 已匹配: <b style="color:var(--color-accent)">${s.matched || 0}</b></p>
      <p>🆕 有新版本: <b style="color:#e6a23c">${s.newer || 0}</b></p>
      <p>📦 版本较旧: <b style="color:#909399">${s.older || 0}</b></p>
      <p>❌ 未找到: <b style="color:#f56c6c">${s.not_found || 0}</b></p>
      <p style="margin-top:10px;color:var(--text-secondary);">赛博化缘完毕，点击下方按钮下载结果 👇</p>
    </div>`,
    '排查结果',
    {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '知道了 ✨',
      customClass: 'batch-dialog',
    }
  )
}

function onUploadError(err: any) {
  ElMessage.error({ message: '上传失败: ' + (err.message || '未知错误，再试一次吧~'), customClass: 'cyber-msg' })
}

function pauseBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/pause`, { method: 'POST' })
  batchStatus.value = 'paused'
  ElMessage.info('批量任务已暂停')
}

function resumeBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/resume`, { method: 'POST' })
  batchStatus.value = 'running'
  ElMessage.info('批量任务已继续')
}

function cancelBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/cancel`, { method: 'POST' })
  batchStatus.value = 'cancelled'
  ElMessage.warning('批量任务已取消')
}

function downloadResult() {
  window.open(`${store.apiBase}/api/batch/${store.batchTaskId}/download`, '_blank')
}

const batchStatusType = computed(() => {
  const map: Record<string, string> = {
    running: 'warning', paused: 'info', completed: 'success', cancelled: 'danger', error: 'danger',
  }
  return map[batchStatus.value] || 'info'
})
</script>

<style scoped>
.batch-panel { }

.batch-card {
  border-radius: var(--radius-xl) !important;
}

.panel-title { font-weight: 700; font-size: 15px; }

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.tip { color: var(--text-muted); font-size: 12px; font-style: italic; }

/* 上传区 */
.batch-upload :deep(.el-upload-dragger) {
  border-radius: var(--radius-lg) !important;
  border: 2px dashed rgba(79, 70, 229, 0.3) !important;
  background: rgba(79, 70, 229, 0.02) !important;
  padding: 36px !important;
  transition: all var(--transition-base) !important;
}
.batch-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--color-primary-light) !important;
  background: rgba(79, 70, 229, 0.05) !important;
  box-shadow: var(--shadow-glow) !important;
}
.upload-icon { font-size: 48px; color: var(--color-primary-light); margin-bottom: 8px; }
.upload-text { font-size: 15px; color: var(--text-primary); }
.upload-text em { color: var(--color-primary); font-style: normal; font-weight: 600; }
.upload-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

/* 进度 */
.batch-progress { }
.task-info {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 10px;
}
.task-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-secondary);
}
.task-progress-text {
  font-weight: 700;
  font-size: 14px;
  color: var(--color-primary);
  margin-left: auto;
}
.batch-bar { margin-bottom: 12px; }
.batch-bar :deep(.el-progress-bar__outer) {
  border-radius: 10px !important;
  background: rgba(148, 163, 184, 0.15) !important;
}
.batch-bar :deep(.el-progress-bar__inner) {
  border-radius: 10px !important;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent)) !important;
}
.task-actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
