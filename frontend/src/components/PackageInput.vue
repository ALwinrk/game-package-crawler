<template>
  <div class="package-input animate-fade-in-up">
    <el-card shadow="never" class="input-card">
      <el-form :model="store" label-width="0">
        <!-- 包名输入 -->
        <el-form-item>
          <el-input
            v-model="store.packageInput"
            placeholder="输入 Android 包名，如 com.tencent.ig（一行一个，赛博化缘中...）"
            type="textarea"
            :rows="3"
            class="glow-input"
            clearable
            @input="onPackageInput"
          />
        </el-form-item>

        <!-- 版本信息 -->
        <el-row :gutter="14">
          <el-col :xs="24" :sm="7">
            <el-input
              v-model="store.expectedVersion"
              :placeholder="memoHintVersion || '期望版本名（可选）'"
              class="glow-input"
              clearable
            >
              <template #prepend><span class="prepend-label">版本名</span></template>
            </el-input>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-input
              v-model="store.expectedVersionCode"
              :placeholder="memoHintCode || '期望版本号（可选）'"
              class="glow-input"
              clearable
            >
              <template #prepend><span class="prepend-label">版本号</span></template>
            </el-input>
          </el-col>
          <el-col :xs="24" :sm="10">
            <el-button
              class="btn-memo"
              :icon="Memo"
              @click="applyMemo"
              :disabled="!store.packageInput.trim()"
              round
            >
              📋 应用上次版本
            </el-button>
          </el-col>
        </el-row>

        <!-- 操作按钮 -->
        <el-row :gutter="14" class="action-row">
          <el-col :xs="24" :sm="8">
            <el-radio-group v-model="store.fetchMode" size="default">
              <el-radio-button value="fast">⚡ 快速排查</el-radio-button>
              <el-radio-button value="slow">🐢 慢速排查</el-radio-button>
              <el-radio-button value="all">🌐 全量排查</el-radio-button>
            </el-radio-group>
          </el-col>
          <el-col :xs="24" :sm="16" class="action-buttons">
            <el-button
              type="primary"
              :icon="Search"
              :loading="store.loading"
              @click="startSearch"
              size="large"
              round
            >
              🔍 {{ store.loading ? '正在抓取中...' : '开始排查' }}
            </el-button>
            <el-button
              :icon="Delete"
              @click="clearResults"
              :disabled="!store.results.length"
              round
            >
              清空结果
            </el-button>
            <el-tooltip
              content="快速排查: Google Play + APKPure + APKCombo (秒级) | 慢速排查: APKMirror + APKVision (30-90s) | 全量排查: 全部站点一起上！"
              placement="bottom"
            >
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-col>
        </el-row>
      </el-form>

      <!-- 解析出的包名列表 -->
      <div v-if="packages.length > 1" class="package-list animate-fade-in-up">
        <el-tag
          v-for="(p, i) in packages"
          :key="i"
          type="info"
          size="small"
          effect="dark"
          class="pkg-tag"
        >
          {{ p }}
        </el-tag>
        <span class="pkg-count">共 {{ packages.length }} 个包名，准备就绪 🚀</span>
      </div>

      <!-- 加载提示 -->
      <div v-if="store.loading" class="search-hint">
        <span class="dot-pulse"></span>
        正在努力爬取，博主可能在写代码...
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, Delete, Memo, QuestionFilled } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage } from 'element-plus'

const store = useAppStore()
const memoHintVersion = ref('')
const memoHintCode = ref('')

const packages = computed(() => {
  return store.packageInput
    .split(/[\n,;]/)
    .map(s => s.trim())
    .filter(Boolean)
})

let debounceTimer: any = null

async function onPackageInput() {
  clearTimeout(debounceTimer)
  memoHintVersion.value = ''
  memoHintCode.value = ''
  debounceTimer = setTimeout(async () => {
    const pkgs = packages.value
    if (pkgs.length === 1 && pkgs[0].length > 3) {
      const memo = await store.checkMemo(pkgs[0])
      if (memo) {
        memoHintVersion.value = `上次: ${memo.version_name || '-'}`
        memoHintCode.value = `上次: ${memo.version_code || '-'}`
      }
    }
  }, 500)
}

async function applyMemo() {
  const pkg = packages.value[0]
  if (!pkg) return
  const memo = await store.checkMemo(pkg)
  if (memo) {
    store.expectedVersion = memo.version_name || ''
    store.expectedVersionCode = memo.version_code || ''
    ElMessage.success({ message: `✨ 已应用 ${pkg} 的版本记录`, customClass: 'cyber-msg' })
  } else {
    ElMessage.info({ message: '这个包名还没有历史记录，先去排查一次吧~', customClass: 'cyber-msg' })
  }
}

async function startSearch() {
  const pkgs = packages.value
  if (!pkgs.length) {
    ElMessage.warning({ message: '哎呀，还没输入包名呢！至少输入一个吧~', customClass: 'cyber-msg' })
    return
  }
  store.results = []
  if (pkgs.length === 1) {
    await store.doFetch(pkgs[0])
  } else {
    ElMessage.info({ message: `正在并发排查 ${pkgs.length} 个包名，喝杯茶等一会吧 🍵`, customClass: 'cyber-msg' })
    await store.doFetchBatch(pkgs)
    ElMessage.success({ message: `🎉 排查完成: ${store.results.length}/${pkgs.length} 个！`, customClass: 'cyber-msg' })
  }
}

function clearResults() {
  store.results = []
}
</script>

<style scoped>
.package-input { margin-bottom: 20px; }

.input-card {
  border-radius: var(--radius-xl) !important;
  overflow: visible;
}

.prepend-label {
  font-weight: 500;
  font-size: 13px;
  color: var(--text-secondary);
}

.action-row {
  margin-top: 14px;
  align-items: center;
}
.action-buttons {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* 记忆按钮 */
.btn-memo {
  width: 100%;
  border: 1.5px dashed rgba(79, 70, 229, 0.35) !important;
  background: transparent !important;
  color: var(--color-primary) !important;
  font-weight: 500;
  transition: all var(--transition-base) !important;
}
.btn-memo:hover {
  background: rgba(79, 70, 229, 0.08) !important;
  border-color: var(--color-primary-light) !important;
  transform: translateY(-1px);
}

.help-icon {
  font-size: 18px;
  color: var(--text-muted);
  cursor: help;
  transition: color var(--transition-fast);
}
.help-icon:hover { color: var(--color-primary-light); }

/* 包名标签 */
.package-list {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.pkg-tag {
  border-radius: 20px !important;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.pkg-count {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}

/* 加载提示 */
.search-hint {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  font-style: italic;
}
.dot-pulse {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: glowPulse 1.5s ease-in-out infinite;
}
</style>
