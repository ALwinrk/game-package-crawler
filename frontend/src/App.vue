<template>
  <div class="app-container">
    <el-container>
      <el-header class="app-header">
        <h1>🎮 游戏包名爬虫系统 v2.0</h1>
        <div class="header-actions">
          <el-tag :type="apiOnline ? 'success' : 'danger'" size="small">
            {{ apiOnline ? 'API 在线' : 'API 离线' }}
          </el-tag>
          <el-button @click="checkApi" size="small" circle>
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
      </el-header>

      <el-main>
        <el-tabs v-model="store.activeTab" type="border-card">
          <!-- 包名排查 -->
          <el-tab-pane label="包名排查" name="search">
            <PackageInput />
            <ResultTable v-if="store.results.length" />
          </el-tab-pane>

          <!-- 批量处理 -->
          <el-tab-pane label="批量处理" name="batch">
            <BatchPanel />
          </el-tab-pane>

          <!-- 下载管理 -->
          <el-tab-pane label="下载管理" name="download">
            <DownloadQueue />
          </el-tab-pane>

          <!-- 设置 -->
          <el-tab-pane label="设置" name="settings">
            <SettingsPanel />
          </el-tab-pane>
        </el-tabs>
      </el-main>

      <el-footer class="app-footer">
        <span>API: {{ store.apiBase }}</span>
        <span>模式: {{ modeLabel }}</span>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useAppStore } from './stores/app'
import PackageInput from './components/PackageInput.vue'
import ResultTable from './components/ResultTable.vue'
import BatchPanel from './components/BatchPanel.vue'
import DownloadQueue from './components/DownloadQueue.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const store = useAppStore()
const apiOnline = ref(false)

const modeLabel = computed(() => {
  const map: Record<string, string> = { fast: '快速排查', slow: '慢速排查', all: '全量排查' }
  return map[store.fetchMode] || '快速排查'
})

async function checkApi() {
  try {
    const resp = await fetch(`${store.apiBase}/api/health`)
    apiOnline.value = resp.ok
  } catch {
    apiOnline.value = false
  }
}

onMounted(() => {
  checkApi()
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Microsoft YaHei', sans-serif; background: #f5f7fa; }
.app-container { min-height: 100vh; }
.app-header {
  display: flex; justify-content: space-between; align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white; padding: 0 24px; height: 60px !important;
}
.app-header h1 { font-size: 20px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.app-footer {
  display: flex; justify-content: space-between; align-items: center;
  background: #fff; border-top: 1px solid #ebeef5;
  padding: 0 24px; height: 36px !important; font-size: 12px; color: #909399;
}
</style>
