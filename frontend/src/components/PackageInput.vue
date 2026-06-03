<template>
  <div class="package-input">
    <el-card shadow="never">
      <el-form :model="store" label-width="0">
        <!-- 包名输入 -->
        <el-form-item>
          <el-input
            v-model="store.packageInput"
            placeholder="输入 Android 包名，如 com.tencent.ig（一行一个）"
            type="textarea"
            :rows="3"
            clearable
            @input="onPackageInput"
          />
        </el-form-item>

        <!-- 版本信息 -->
        <el-row :gutter="16">
          <el-col :span="8">
            <el-input v-model="store.expectedVersion" placeholder="期望版本名（可选）" clearable>
              <template #prepend>版本名</template>
            </el-input>
          </el-col>
          <el-col :span="8">
            <el-input v-model="store.expectedVersionCode" placeholder="期望版本号（可选）" clearable>
              <template #prepend>版本号</template>
            </el-input>
          </el-col>
          <el-col :span="8">
            <el-button type="primary" :icon="Memo" @click="applyMemo" :disabled="!store.packageInput.trim()">
              应用上次版本
            </el-button>
          </el-col>
        </el-row>

        <!-- 操作按钮 -->
        <el-row :gutter="16" style="margin-top: 12px;">
          <el-col :span="4">
            <el-radio-group v-model="store.fetchMode">
              <el-radio-button value="fast">快速排查</el-radio-button>
              <el-radio-button value="slow" disabled>慢速排查</el-radio-button>
              <el-radio-button value="all">全量排查</el-radio-button>
            </el-radio-group>
          </el-col>
          <el-col :span="12">
            <el-button type="success" :icon="Search" :loading="store.loading" @click="startSearch" size="large">
              开始排查
            </el-button>
            <el-button :icon="Delete" @click="clearResults" :disabled="!store.results.length">
              清空结果
            </el-button>
            <el-tooltip content="快速排查: Google Play + APKPure + APKCombo (秒级)">
              <el-icon><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-col>
        </el-row>
      </el-form>

      <!-- 解析出的包名列表 -->
      <div v-if="packages.length > 1" class="package-list">
        <el-tag v-for="(p, i) in packages" :key="i" type="info" size="small" style="margin: 2px;">
          {{ p }}
        </el-tag>
        <span class="text-secondary">共 {{ packages.length }} 个包名</span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Search, Delete, Memo, QuestionFilled } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { ElMessage } from 'element-plus'

const store = useAppStore()

const packages = computed(() => {
  return store.packageInput
    .split(/[\n,;]/)
    .map(s => s.trim())
    .filter(Boolean)
})

let debounceTimer: any = null

function onPackageInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    const pkgs = packages.value
    if (pkgs.length === 1) {
      const memo = await store.checkMemo(pkgs[0])
      // 不自动填充，等用户点击按钮
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
    ElMessage.success(`已应用 ${pkg} 的版本: ${memo.version_name || memo.version_code}`)
  } else {
    ElMessage.info('该包名没有历史记录')
  }
}

async function startSearch() {
  const pkgs = packages.value
  if (!pkgs.length) {
    ElMessage.warning('请输入至少一个包名')
    return
  }
  store.results = []
  if (pkgs.length === 1) {
    await store.doFetch(pkgs[0])
  } else {
    ElMessage.info(`正在并发排查 ${pkgs.length} 个包名...`)
    await store.doFetchBatch(pkgs)
    ElMessage.success(`排查完成: ${store.results.length}/${pkgs.length} 个`)
  }
}

function clearResults() {
  store.results = []
}
</script>

<style scoped>
.package-input { margin-bottom: 16px; }
.package-list { margin-top: 8px; }
.text-secondary { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
