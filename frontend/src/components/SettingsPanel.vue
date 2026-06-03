<template>
  <div class="settings-panel">
    <el-card shadow="never">
      <template #header><span>系统设置</span></template>

      <el-form :model="config" label-width="140px" label-position="left">
        <!-- 代理 -->
        <el-form-item label="代理地址">
          <el-input v-model="config.proxy" placeholder="http://127.0.0.1:7897" />
        </el-form-item>

        <!-- 下载路径 -->
        <el-form-item label="下载目录">
          <el-input v-model="config.download_path" placeholder="./downloads" />
        </el-form-item>

        <!-- 并发数 -->
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="爬虫并发数">
              <el-input-number v-model="config.scraper_concurrency" :min="1" :max="10" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="下载并发数">
              <el-input-number v-model="config.download_concurrency" :min="1" :max="5" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 重试 -->
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="重试次数">
              <el-input-number v-model="config.retry_times" :min="0" :max="5" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="重试延迟(s)">
              <el-input-number v-model="config.retry_delay" :min="0.5" :max="10" :step="0.5" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 超时 -->
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="请求超时(s)">
              <el-input-number v-model="config.request_timeout" :min="5" :max="60" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="浏览器超时(s)">
              <el-input-number v-model="config.stealth_timeout" :min="15" :max="120" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 启用站点 -->
        <el-form-item label="启用站点">
          <el-checkbox-group v-model="config.enabled_sites">
            <el-checkbox value="google_play" label="Google Play" />
            <el-checkbox value="apkpure" label="APKPure" />
            <el-checkbox value="apkcombo" label="APKCombo" />
            <el-checkbox value="apkmirror" label="APKMirror" />
            <el-checkbox value="apkvision" label="APKVision" />
          </el-checkbox-group>
        </el-form-item>

        <!-- Google Play Cookie -->
        <el-form-item label="GP Cookie 文件">
          <el-input v-model="config.google_play_cookie_path" placeholder="留空则不使用 Cookie" />
        </el-form-item>

        <!-- 语言 -->
        <el-form-item label="界面语言">
          <el-radio-group v-model="config.language">
            <el-radio value="zh">中文</el-radio>
            <el-radio value="en">English</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 操作 -->
        <el-form-item>
          <el-button type="primary" :icon="Check" @click="saveConfig" :loading="saving">保存设置</el-button>
          <el-button :icon="RefreshRight" @click="loadConfig">恢复默认</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 记忆化管理 -->
    <el-card shadow="never" style="margin-top: 16px;">
      <template #header>
        <div class="panel-header">
          <span>版本记忆管理</span>
          <el-button :icon="Refresh" size="small" @click="loadMemo" :loading="memoLoading">刷新</el-button>
        </div>
      </template>

      <el-empty v-if="!memoList.length" description="暂无记忆数据" />

      <el-table v-else :data="memoList" stripe size="small">
        <el-table-column prop="package_name" label="包名" width="300" />
        <el-table-column prop="version_code" label="版本号" width="120" />
        <el-table-column prop="version_name" label="版本名" width="120" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="deleteMemo(row.package_name)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Check, RefreshRight, Refresh } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage } from 'element-plus'

const store = useAppStore()
const saving = ref(false)
const memoLoading = ref(false)
const memoList = ref<any[]>([])

const config = reactive({
  proxy: 'http://127.0.0.1:7897',
  download_path: './downloads',
  scraper_concurrency: 4,
  download_concurrency: 3,
  retry_times: 2,
  retry_delay: 1.0,
  request_timeout: 10.0,
  stealth_timeout: 60.0,
  enabled_sites: ['google_play', 'apkpure', 'apkcombo', 'apkmirror', 'apkvision'],
  google_play_cookie_path: '',
  language: 'zh',
})

async function loadConfig() {
  try {
    const resp = await fetch(`${store.apiBase}/api/config`)
    const data = await resp.json()
    Object.assign(config, data)
  } catch { }
}

async function saveConfig() {
  saving.value = true
  try {
    await fetch(`${store.apiBase}/api/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    ElMessage.success('设置已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function loadMemo() {
  memoLoading.value = true
  try {
    const resp = await fetch(`${store.apiBase}/api/memo`)
    const data = await resp.json()
    memoList.value = data.items || []
  } catch { }
  memoLoading.value = false
}

async function deleteMemo(pkg: string) {
  try {
    await fetch(`${store.apiBase}/api/memo/${pkg}`, { method: 'DELETE' })
    ElMessage.success(`已删除 ${pkg} 的记忆`)
    loadMemo()
  } catch { }
}

onMounted(() => {
  loadConfig()
  loadMemo()
})
</script>

<style scoped>
.panel-header { display: flex; justify-content: space-between; align-items: center; }
</style>
