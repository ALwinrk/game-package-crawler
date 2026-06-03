<template>
  <div class="batch-panel">
    <el-card shadow="never">
      <template #header>
        <div class="panel-header">
          <span>批量 Excel 排查</span>
          <span class="tip">支持 .xlsx / .xls，自动检测 package_name 列</span>
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
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽 Excel 文件到此处 或 <em>点击上传</em>
        </div>
      </el-upload>

      <!-- 进度 -->
      <div v-if="store.batchTaskId" class="batch-progress" style="margin-top: 16px;">
        <el-divider />
        <div class="task-info">
          <span>任务 ID: {{ store.batchTaskId }}</span>
          <el-tag :type="batchStatusType">{{ batchStatus }}</el-tag>
        </div>
        <el-progress
          :percentage="store.batchProgress"
          :status="store.batchProgress >= 100 ? 'success' : undefined"
          :text-inside="true"
          :stroke-width="22"
          style="margin-top: 12px;"
        />
        <div class="task-actions" style="margin-top: 12px;">
          <el-button size="small" @click="pauseBatch" :disabled="batchStatus !== 'running'">
            暂停
          </el-button>
          <el-button size="small" @click="resumeBatch" :disabled="batchStatus !== 'paused'">
            继续
          </el-button>
          <el-button size="small" type="danger" @click="cancelBatch" :disabled="batchStatus === 'completed'">
            取消
          </el-button>
          <el-button
            v-if="batchStatus === 'completed'"
            size="small" type="success"
            @click="downloadResult"
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
import { UploadFilled } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useAppStore()

const batchStatus = ref('')
const uploadRef = ref()
const batchSummary = ref<any>(null)

function onUploadSuccess(resp: any) {
  store.batchTaskId = resp.task_id
  store.batchTotal = resp.total
  batchStatus.value = 'running'
  batchSummary.value = null
  ElMessage.success(`批量任务已启动: ${resp.filename} (${resp.total} 行)`)

  // WebSocket 订阅进度
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
    `<div style="line-height:2">
      <p><b>排查完成!</b> 共 ${store.batchTotal} 个包名</p>
      <p style="color:#67c23a">已匹配: ${s.matched || 0}</p>
      <p style="color:#e6a23c">有新版本: ${s.newer || 0}</p>
      <p style="color:#909399">版本较旧: ${s.older || 0}</p>
      <p style="color:#f56c6c">未找到: ${s.not_found || 0}</p>
      <p style="margin-top:8px">点击"下载结果 Excel"获取完整文件</p>
    </div>`,
    '排查结果',
    { dangerouslyUseHTMLString: true, confirmButtonText: '知道了' }
  )
}

function onUploadError(err: any) {
  ElMessage.error('上传失败: ' + (err.message || '未知错误'))
}

function pauseBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/pause`, { method: 'POST' })
  batchStatus.value = 'paused'
}

function resumeBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/resume`, { method: 'POST' })
  batchStatus.value = 'running'
}

function cancelBatch() {
  fetch(`${store.apiBase}/api/batch/${store.batchTaskId}/cancel`, { method: 'POST' })
  batchStatus.value = 'cancelled'
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
.panel-header { display: flex; justify-content: space-between; }
.tip { color: #909399; font-size: 12px; }
.task-info { display: flex; gap: 12px; align-items: center; }
.task-actions { display: flex; gap: 8px; }
</style>
