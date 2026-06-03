<template>
  <div class="result-table" v-for="(result, idx) in store.results" :key="idx">
    <el-card shadow="never">
      <!-- 摘要 -->
      <template #header>
        <div class="result-header">
          <span class="package-name">{{ result.package }}</span>
          <el-tag v-if="result.best_version" type="success" size="large">
            {{ result.best_version }}
            <span v-if="result.best_version_code">(vc: {{ result.best_version_code }})</span>
          </el-tag>
          <el-tag :type="statusTagType(result.compare_status)">
            {{ statusLabel(result.compare_status) }}
          </el-tag>
          <!-- 版本名对比 -->
          <span v-if="result.version_name_compare" class="compare-detail">{{ result.version_name_compare }}</span>
          <!-- 版本号对比 -->
          <span v-if="result.version_code_compare" class="compare-detail">{{ result.version_code_compare }}</span>
          <span v-if="result.error" class="error-text">{{ result.error }}</span>
        </div>
      </template>

      <!-- 各站点详情表格 -->
      <el-table :data="getSourceRows(result)" stripe size="small">
        <el-table-column prop="source" label="数据源" width="120" />
        <el-table-column prop="version" label="版本名" width="120">
          <template #default="{ row }">
            <span v-if="row.version" class="version-text">{{ row.version }}</span>
            <span v-else class="no-version">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="version_code" label="版本号" width="100">
          <template #default="{ row }">
            <span v-if="row.version_code">{{ row.version_code }}</span>
            <span v-else class="no-version">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="release_date" label="发布日期" width="140" />
        <el-table-column prop="file_size" label="大小" width="80" />
        <el-table-column prop="error" label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else class="ok-text">OK</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button
              v-if="row.detail_url"
              size="small"
              type="primary"
              link
              @click="openUrl(row.detail_url)"
            >
              详情页
            </el-button>
            <el-button
              v-if="row.version && !row.download_urls.length"
              size="small"
              type="success"
              link
              :loading="row._extracting"
              @click="extractAndDownload(row)"
            >
              获取链接
            </el-button>
            <el-button
              v-for="(durl, i) in row.download_urls"
              :key="'dl-'+i"
              size="small"
              type="warning"
              link
              @click="openUrl(durl)"
            >
              浏览器下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
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
    matched: '已匹配', newer: '有新版本', older: '版本较旧',
    not_found: '未找到', error: '错误',
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

function openUrl(url: string) {
  window.open(url, '_blank')
}

async function extractAndDownload(row: RowData) {
  row._extracting = true
  try {
    const data = await store.extractLinks(row.source, row.detail_url!, row.package)
    if (data?.best) {
      row.download_urls = [data.best.url]
      if (data.best.arch) row.abis = [data.best.arch]
      await store.submitDownload(data.best.url, row.package, row.version || 'latest', data.best.arch || 'unknown', row.detail_url || '')
      ElMessage.success(`已提交下载: ${data.best.arch}`)
    } else if (data?.variants?.length) {
      row.download_urls = data.variants.map((v: any) => v.url)
      ElMessage.info(`找到 ${data.variants.length} 个变体，请选择`)
    } else {
      ElMessage.warning('未找到下载链接')
    }
  } catch (e: any) {
    ElMessage.error(`提取失败: ${e.message}`)
  } finally {
    row._extracting = false
  }
}

async function downloadApk(url: string, row: RowData, pkg: string) {
  const arch = row.abis?.[0] || 'unknown'
  await store.submitDownload(url, pkg, row.version || 'latest', arch)
  ElMessage.success('已添加到下载队列')
}
</script>

<style scoped>
.result-table { margin-bottom: 16px; }
.result-header { display: flex; gap: 12px; align-items: center; }
.package-name { font-weight: bold; font-size: 16px; font-family: monospace; }
.version-text { color: #67c23a; font-weight: bold; }
.no-version { color: #c0c4cc; }
.ok-text { color: #67c23a; font-size: 12px; }
.error-text { color: #f56c6c; font-size: 12px; }
</style>
