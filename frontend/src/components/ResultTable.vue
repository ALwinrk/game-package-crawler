<template>
  <div class="result-table" v-for="(result, idx) in store.results" :key="result.package || idx" :style="{ animationDelay: `${idx * 0.08}s` }">
    <el-card shadow="never" class="result-card animate-fade-in-up">
      <!-- 摘要 -->
      <template #header>
        <div class="result-header">
          <span class="package-name">{{ result.package }}</span>
          <el-tag
            v-if="result.best_version"
            type="success"
            size="large"
            effect="dark"
            round
            class="version-tag"
          >
            {{ result.best_version }}
            <span v-if="result.best_version_code" class="vc-badge">vc:{{ result.best_version_code }}</span>
          </el-tag>
          <el-tag
            :type="statusTagType(result.compare_status)"
            size="large"
            effect="dark"
            round
            class="status-tag"
          >
            {{ statusLabel(result.compare_status) }}
          </el-tag>
          <span v-if="result.version_name_compare" class="compare-detail">{{ result.version_name_compare }}</span>
          <span v-if="result.version_code_compare" class="compare-detail">{{ result.version_code_compare }}</span>
          <span v-if="result.error" class="error-text">😵 {{ result.error }}</span>
        </div>
      </template>

      <!-- 游戏信息卡片 (v2.5: 中文名 + 更新内容) -->
      <div v-if="result.app_name || result.whats_new" class="app-info-card">
        <div v-if="result.app_name" class="app-title-line">
          <span class="app-cn-name">{{ result.app_name }}</span>
          <span class="app-pkg-name">({{ result.package }})</span>
        </div>
        <div v-if="result.whats_new" class="app-whats-new">
          <div class="whats-new-label">📝 更新内容：</div>
          <div class="whats-new-body">{{ result.whats_new }}</div>
        </div>
        <div v-else class="app-whats-new empty-whats-new">
          暂无更新内容
        </div>
      </div>

      <!-- 各站点详情表格 -->
      <el-table
        :data="getSourceRows(result)"
        stripe
        size="small"
        class="source-table"
      >
        <el-table-column prop="source" label="数据源" width="130">
          <template #default="{ row }">
            <span class="source-name">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本名" width="120">
          <template #default="{ row }">
            <span v-if="row.version" class="version-text">{{ row.version }}</span>
            <span v-else class="no-version">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="version_code" label="版本号" width="110">
          <template #default="{ row }">
            <span v-if="row.version_code" class="vc-mono">{{ row.version_code }}</span>
            <span v-else class="no-version">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="release_date" label="发布日期" width="120">
          <template #default="{ row }">
            <span v-if="row.release_date">{{ row.release_date }}</span>
            <span v-else class="no-version">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="大小" width="90" />
        <el-table-column prop="error" label="状态" min-width="180">
          <template #default="{ row }">
            <el-tag v-if="row.error" type="danger" size="small" effect="plain" round>{{ row.error }}</el-tag>
            <el-tag v-else type="success" size="small" effect="plain" round>✅ OK</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <!-- 按钮 1: 中文站详情页 -->
            <el-tooltip
              v-if="row.detail_url"
              :content="'打开 ' + row.source + ' 中文详情页'"
              placement="top"
            >
              <el-button
                size="small"
                type="primary"
                link
                @click="openDetailUrl(row.detail_url, row.source)"
              >
                🌐 详情页
              </el-button>
            </el-tooltip>

            <!-- 按钮 2: 浏览器自主下载（打开下载页） -->
            <el-tooltip
              v-if="row.version && !row.error"
              content="在浏览器中打开下载页面，手动下载"
              placement="top"
            >
              <el-button
                size="small"
                type="warning"
                link
                :icon="VideoPlay"
                @click="openDownloadPage(row)"
              >
                浏览器下载
              </el-button>
            </el-tooltip>

            <!-- 按钮 3: 系统自动下载 -->
            <el-tooltip
              v-if="row.version && !row.error"
              content="系统自动提取链接并下载，无需手动操作"
              placement="top"
            >
              <el-button
                size="small"
                type="success"
                :icon="Download"
                :loading="row._extracting"
                @click="extractAndDownload(row)"
              >
                点击下载
              </el-button>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Download, VideoPlay } from '@element-plus/icons-vue'
import { useAppStore, type FetchResult, type SourceResult } from '../stores/app'
import { ElMessage } from 'element-plus'

const store = useAppStore()

interface RowData extends SourceResult {
  _extracting?: boolean
}

function getSourceRows(result: FetchResult): RowData[] {
  return Object.values(result.results).map(r => ({ ...r }))
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    matched: '✅ 已匹配', newer: '🆕 有新版本', older: '📦 版本较旧',
    not_found: '❌ 未找到', error: '💥 错误',
  }
  return map[s] || s
}

function statusTagType(s: string): string {
  const map: Record<string, string> = {
    matched: 'success', newer: 'warning', older: 'info',
    not_found: 'danger', error: 'danger',
  }
  return map[s] || 'info'
}

/** v2.8: 根据站点追加语言参数，防止服务器重定向到国际站 */
function openDetailUrl(url: string, source: string) {
  if (!url) return
  let finalUrl = url

  if (source === 'Google Play') {
    if (!finalUrl.includes('hl=')) {
      finalUrl += (finalUrl.includes('?') ? '&' : '?') + 'hl=zh_CN'
    }
  } else if (source === 'APKPure') {
    if (!finalUrl.includes('apkpure.com/cn/') && !finalUrl.includes('apkpure.net/cn/')) {
      finalUrl = finalUrl.replace('apkpure.com/', 'apkpure.com/cn/')
      finalUrl = finalUrl.replace('apkpure.net/', 'apkpure.com/cn/')
    }
  } else if (source === 'APKCombo') {
    if (!finalUrl.includes('/zh/')) {
      if (finalUrl.includes('/api/app/')) {
        // API URL: 提取包名，重建为中文详情页 URL
        const pkg = finalUrl.split('/api/app/').pop() || ''
        if (pkg) finalUrl = 'https://apkcombo.com/zh/' + pkg
      } else {
        finalUrl = finalUrl.replace('apkcombo.com/', 'apkcombo.com/zh/')
      }
    }
  }

  window.open(finalUrl, '_blank')
}

/** v3.3: 打开浏览器下载页 — 调用后端 API 获取正确的下载页 URL */
async function openDownloadPage(row: RowData) {
  try {
    const data = await store.extractLinks(row.source, row.detail_url!, row.package, row.version || '')
    const dlUrl = data?.download_page_url || data?.best?.url
    if (dlUrl) {
      window.open(dlUrl, '_blank')
      ElMessage.success({ message: '已打开下载页，请在浏览器中手动下载', customClass: 'cyber-msg' })
    } else {
      // 回退：直接用详情页
      openDetailUrl(row.detail_url!, row.source)
      ElMessage.info({ message: '未找到下载页，已打开详情页', customClass: 'cyber-msg' })
    }
  } catch (e: any) {
    ElMessage.error({ message: '获取下载页失败', customClass: 'cyber-msg' })
  }
}

/** v3.3: 系统自动下载 — 提取链接 → 提交下载 → Playwright/aiohttp */
async function extractAndDownload(row: RowData) {
  row._extracting = true
  try {
    const data = await store.extractLinks(row.source, row.detail_url!, row.package, row.version || '')
    const dlUrl = data?.best?.url
    if (dlUrl) {
      await store.submitDownload(dlUrl, row.package, row.version || 'latest', data.best.arch || 'unknown', row.detail_url || '')
      ElMessage.success({ message: `📥 已提交下载: ${data.best.arch || '自动'}`, customClass: 'cyber-msg' })
    } else {
      ElMessage.warning({ message: '哎呀，没找到下载链接，请尝试"浏览器下载"手动操作~', customClass: 'cyber-msg' })
    }
  } catch (e: any) {
    ElMessage.error({ message: `下载失败: ${e.message}`, customClass: 'cyber-msg' })
  } finally {
    row._extracting = false
  }
}
</script>

<style scoped>
.result-table {
  margin-bottom: 18px;
  animation: fadeInUp 0.4s ease both;
}

.result-card {
  border-radius: var(--radius-xl) !important;
}

.result-header {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.package-name {
  font-weight: 700;
  font-size: 15px;
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  color: var(--text-primary);
}

.version-tag {
  font-weight: 600 !important;
}
.vc-badge {
  opacity: 0.8;
  font-weight: 400;
  font-size: 12px;
}

.status-tag {
  font-weight: 600 !important;
}

.compare-detail {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
  background: rgba(148, 163, 184, 0.1);
  padding: 2px 10px;
  border-radius: 12px;
}

.version-text { color: var(--color-accent); font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.vc-mono { font-family: 'JetBrains Mono', monospace; font-weight: 500; }
.no-version { color: var(--text-muted); }
.error-text { color: #f56c6c; font-size: 12px; }

.source-name { font-weight: 600; }

.source-table {
  border-radius: var(--radius-md);
  overflow: hidden;
}

/* ── 游戏信息卡片 (v2.5) ── */
.app-info-card {
  margin-bottom: 16px;
  padding: 14px 18px;
  background: rgba(79, 70, 229, 0.04);
  border: 1px solid rgba(79, 70, 229, 0.12);
  border-radius: var(--radius-md);
}
.app-title-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}
.app-cn-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
}
.app-pkg-name {
  font-size: 13px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}
.app-whats-new {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.whats-new-label {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text-primary);
}
.whats-new-body {
  white-space: pre-wrap;
  word-break: break-word;
}
.empty-whats-new {
  color: var(--text-muted);
  font-style: italic;
}
</style>
