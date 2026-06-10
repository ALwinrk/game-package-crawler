<template>
  <div class="settings-panel animate-fade-in-up">
    <!-- 主题切换 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span>🎨 界面主题</span>
          <el-switch
            :model-value="store.darkMode"
            :active-icon="Moon"
            :inactive-icon="Sunny"
            inline-prompt
            @change="store.toggleDark()"
          />
        </div>
      </template>
    </el-card>

    <!-- 系统设置 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">⚙️ 系统设置</span>
      </template>

      <el-form :model="config" label-width="150px" label-position="left">
        <!-- 代理 + 下载路径 -->
        <div class="setting-group">
          <div class="group-title">🌐 网络</div>
          <el-form-item label="代理地址">
            <el-input v-model="config.proxy" placeholder="http://127.0.0.1:7897" class="glow-input">
              <template #append>
                <el-button :icon="Link" @click="testProxy" :loading="testingProxy">测试</el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="下载目录">
            <el-input v-model="config.download_path" placeholder="./downloads" class="glow-input" />
          </el-form-item>
        </div>

        <!-- 并发 -->
        <div class="setting-group">
          <div class="group-title">⚡ 并发控制</div>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="爬虫并发数">
                <el-input-number v-model="config.scraper_concurrency" :min="1" :max="10" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="下载并发数">
                <el-input-number v-model="config.download_concurrency" :min="1" :max="8" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="批量并发数">
                <el-input-number v-model="config.batch_concurrency" :min="1" :max="10" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 重试 + 超时 -->
        <div class="setting-group">
          <div class="group-title">⏱️ 重试 & 超时</div>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="重试次数">
                <el-input-number v-model="config.retry_times" :min="0" :max="5" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="重试延迟(s)">
                <el-input-number v-model="config.retry_delay" :min="0.5" :max="10" :step="0.5" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="缓存TTL(s)">
                <el-input-number v-model="config.cache_ttl_seconds" :min="30" :max="3600" :step="30" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16" class="row-mt">
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
        </div>

        <!-- 站点 -->
        <div class="setting-group">
          <div class="group-title">📡 启用站点</div>
          <el-form-item label="">
            <el-checkbox-group v-model="config.enabled_sites">
              <el-checkbox value="google_play" label="Google Play" />
              <el-checkbox value="apkpure" label="APKPure" />
              <el-checkbox value="apkcombo" label="APKCombo" />
              <el-checkbox value="apkmirror" label="APKMirror" />
              <el-checkbox value="apkvision" label="APKVision" />
            </el-checkbox-group>
          </el-form-item>
        </div>

        <!-- GP Cookie -->
        <div class="setting-group">
          <div class="group-title">🍪 Google Play</div>
          <el-form-item label="Cookie 文件">
            <el-input v-model="config.google_play_cookie_path" placeholder="留空则不使用 Cookie" class="glow-input" />
          </el-form-item>
        </div>

        <!-- 操作 -->
        <el-form-item>
          <el-button type="primary" :icon="Check" @click="saveConfig" :loading="saving" round>
            💾 保存设置
          </el-button>
          <el-button :icon="RefreshRight" @click="loadConfig" round>
            重新加载
          </el-button>
          <el-button :icon="Delete" @click="clearCache" type="danger" plain round>
            清除缓存
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 记忆化管理 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <div class="panel-header">
          <span class="card-title">🧠 版本记忆管理</span>
          <el-button :icon="Refresh" size="small" @click="loadMemo" :loading="memoLoading" round>
            刷新
          </el-button>
        </div>
      </template>

      <div v-if="!memoList.length" class="empty-memo">
        <span>🧠</span>
        <p>暂无记忆数据，排查完成后会自动记录 ✨</p>
      </div>

      <el-table v-else :data="memoList" stripe size="small" class="memo-table">
        <el-table-column prop="package_name" label="包名" min-width="240">
          <template #default="{ row }">
            <span class="memo-pkg">{{ row.package_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="version_code" label="版本号" width="120" />
        <el-table-column prop="version_name" label="版本名" width="120" />
        <el-table-column prop="updated_at" label="更新时间" width="170" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link :icon="Delete" @click="deleteMemo(row.package_name)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- v3.6: 系统公告设置 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">📢 系统公告</span>
      </template>
      <el-form :model="config" label-width="100px" label-position="left">
        <el-form-item label="启用公告">
          <el-switch v-model="config.notice_enabled" />
          <span class="form-hint">关闭后顶部公告栏将隐藏</span>
        </el-form-item>
        <el-form-item v-if="config.notice_enabled" label="公告内容">
          <el-input
            v-model="config.notice_text"
            type="textarea"
            :rows="5"
            placeholder="支持 HTML 标签，例如：&lt;strong&gt;重要通知&lt;/strong&gt; &amp;nbsp;|&amp;nbsp; 内容..."
          />
          <div class="form-hint" style="margin-top: 4px;">
            支持 HTML：&lt;strong&gt;加粗&lt;/strong&gt;、&lt;a href="..."&gt;链接&lt;/a&gt; 等
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Check" @click="saveConfig" :loading="saving" round>
            💾 保存设置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Check, RefreshRight, Refresh, Delete, Link, Moon, Sunny } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage } from 'element-plus'

const store = useAppStore()
const saving = ref(false)
const memoLoading = ref(false)
const testingProxy = ref(false)
const memoList = ref<any[]>([])

const config = reactive({
  proxy: 'http://127.0.0.1:7897',
  download_path: './downloads',
  scraper_concurrency: 4,
  download_concurrency: 3,
  batch_concurrency: 5,
  cache_ttl_seconds: 300,
  retry_times: 2,
  retry_delay: 1.0,
  request_timeout: 10.0,
  stealth_timeout: 60.0,
  enabled_sites: ['google_play', 'apkpure', 'apkcombo', 'apkmirror', 'apkvision'],
  google_play_cookie_path: '',
  notice_enabled: false,
  notice_text: '',
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
    const resp = await fetch(`${store.apiBase}/api/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
      throw new Error(err.detail || `保存失败 (${resp.status})`)
    }
    ElMessage.success({ message: '💾 设置已保存！', customClass: 'cyber-msg' })
  } catch (e: any) {
    ElMessage.error({ message: e?.message || '保存失败，检查下代理或网络吧~', customClass: 'cyber-msg' })
  } finally {
    saving.value = false
  }
}

async function testProxy() {
  if (!config.proxy) {
    ElMessage.warning('请先填写代理地址')
    return
  }
  testingProxy.value = true
  try {
    const resp = await fetch(`${store.apiBase}/api/test-proxy`, { method: 'POST' })
    const data = await resp.json()
    if (data.ok) {
      ElMessage.success({ message: `✅ 代理连接正常 (${data.latency_ms}ms)`, customClass: 'cyber-msg' })
    } else {
      ElMessage.warning({ message: `⚠️ ${data.error || '代理可能不太稳定...'}`, customClass: 'cyber-msg' })
    }
  } catch {
    ElMessage.error({ message: '代理连接失败，检查下配置吧~', customClass: 'cyber-msg' })
  }
  testingProxy.value = false
}

async function clearCache() {
  try {
    const resp = await fetch(`${store.apiBase}/api/cache/clear`, { method: 'POST' })
    const data = await resp.json()
    ElMessage.success({ message: `🧹 已清除 ${data.cleared} 条缓存`, customClass: 'cyber-msg' })
  } catch {
    ElMessage.error({ message: '清除缓存失败', customClass: 'cyber-msg' })
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
    ElMessage.success({ message: `🗑️ 已删除 ${pkg} 的记忆`, customClass: 'cyber-msg' })
    loadMemo()
  } catch { }
}

onMounted(() => {
  loadConfig()
  loadMemo()
})
</script>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 900px;
}

.settings-card {
  border-radius: var(--radius-xl) !important;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
}

.card-title { font-weight: 700; font-size: 15px; }

/* 设置分组 */
.setting-group {
  margin-bottom: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}
.setting-group:last-of-type { border-bottom: none; }
.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-light);
  margin-bottom: 12px;
  padding-left: 4px;
}

.row-mt { margin-top: 4px; }

/* 记忆 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.empty-memo {
  text-align: center;
  padding: 36px 20px;
  color: var(--text-muted);
}
.empty-memo span { font-size: 36px; }
.empty-memo p { font-size: 13px; margin-top: 8px; }

.memo-table { border-radius: var(--radius-md); overflow: hidden; }
.memo-pkg {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 500;
}
</style>
