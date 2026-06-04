<template>
  <div class="app-root" :class="{ 'dark-mode': store.darkMode }">
    <!-- 动态背景 -->
    <div class="bg-animated"></div>

    <!-- v2.8: 后端就绪检查 + 加载屏幕 -->
    <div v-if="!backendReady" class="loading-screen">
      <div class="loading-content">
        <span class="loading-logo">🚀</span>
        <h2>游戏包名爬虫系统 v2.8</h2>
        <p class="loading-text">正在唤醒后端服务，请稍候...</p>
        <el-progress :percentage="loadingDots" :indeterminate="true" :stroke-width="4" color="var(--color-primary)" class="loading-bar" />
        <p class="loading-sub">首次启动需初始化浏览器引擎 (约 3-5 秒)</p>
      </div>
    </div>

    <el-container v-else class="app-shell">
      <!-- 顶部导航栏 — 毛玻璃 -->
      <el-header class="app-header glass-header">
        <div class="header-left">
          <span class="header-logo">🎮</span>
          <h1 class="header-title">游戏包名爬虫系统 <span class="version-tag">v2.8</span></h1>
        </div>
        <div class="header-right">
          <el-tooltip :content="store.darkMode ? '切换浅色模式' : '切换深色模式'" placement="bottom">
            <el-button class="theme-btn" circle @click="store.toggleDark()">
              <el-icon :size="18"><Moon v-if="!store.darkMode" /><Sunny v-else /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tag :type="apiOnline ? 'success' : 'danger'" size="small" effect="dark" round>
            {{ apiOnline ? '⚡ API 在线' : '💀 API 离线' }}
          </el-tag>
        </div>
      </el-header>

      <!-- 主体 -->
      <el-main class="app-main">
        <el-tabs v-model="store.activeTab" type="border-card" class="main-tabs">
          <el-tab-pane name="search">
            <template #label>
              <span class="tab-label">🔍 包名排查</span>
            </template>
            <div class="tab-content animate-fade-in-scale">
              <PackageInput />
              <ResultTable v-if="store.results.length" />
              <!-- 空状态 -->
              <div v-else class="empty-state">
                <div class="empty-icon">🕵️</div>
                <p class="empty-text">输入包名，一键捉虫~</p>
                <p class="empty-sub">支持 Google Play / APKPure / APKCombo / APKMirror / APKVision 五大源</p>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="batch">
            <template #label>
              <span class="tab-label">📦 批量处理</span>
            </template>
            <div class="tab-content animate-fade-in-scale">
              <BatchPanel />
            </div>
          </el-tab-pane>

          <el-tab-pane name="download">
            <template #label>
              <span class="tab-label">📥 下载管理</span>
            </template>
            <div class="tab-content animate-fade-in-scale">
              <DownloadQueue />
            </div>
          </el-tab-pane>

          <el-tab-pane name="settings">
            <template #label>
              <span class="tab-label">⚙️ 设置</span>
            </template>
            <div class="tab-content animate-fade-in-scale">
              <SettingsPanel />
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-main>

      <!-- 底部 -->
      <el-footer class="app-footer glass-header">
        <span class="footer-text">API: {{ store.apiBase }}</span>
        <span class="footer-quote">「{{ randomQuote }}」</span>
        <span class="footer-text">模式: {{ modeLabel }}</span>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Refresh, Moon, Sunny } from '@element-plus/icons-vue'
import { useAppStore } from './stores/app'
import PackageInput from './components/PackageInput.vue'
import ResultTable from './components/ResultTable.vue'
import BatchPanel from './components/BatchPanel.vue'
import DownloadQueue from './components/DownloadQueue.vue'
import SettingsPanel from './components/SettingsPanel.vue'

const store = useAppStore()
const apiOnline = ref(false)
const backendReady = ref(false)
const loadingDots = ref(0)

// v2.8: 轮询后端就绪状态
async function checkReady() {
  try {
    const resp = await fetch(`${store.apiBase}/api/ready`)
    const data = await resp.json()
    if (data.status === 'ready') {
      backendReady.value = true
      return
    }
  } catch { }
  setTimeout(checkReady, 500)
}

// 初始化深色模式
onMounted(() => {
  store.initDarkMode()
  checkReady()
  checkApi()
})

// 幽默随机语录
const quotes = [
  '正在努力爬取，博主可能在写代码...',
  '扫码即功德，打赏即缘分。施主，随喜赞叹啊！',
  '这个功能还在摸鱼，改天再说吧~',
  'APK 云化缘中，请稍候...',
  '赛博捉虫，功德无量 🙏',
  '今日爬取次数已达标，可以躺平了',
]
const randomQuote = computed(() => quotes[Math.floor(Math.random() * quotes.length)])

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

// 初始化深色模式
onMounted(() => {
  store.initDarkMode()
  checkApi()
})
</script>

<style scoped>
/* ── 加载屏幕 (v2.8) ─────────────────────── */
.loading-screen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
}
.loading-content {
  text-align: center;
  animation: fadeInUp 0.6s ease;
}
.loading-logo { font-size: 64px; display: block; margin-bottom: 16px; animation: glowPulse 2s ease-in-out infinite; }
.loading-content h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
}
.loading-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 20px;
}
.loading-bar { width: 240px; margin: 0 auto 12px; }
.loading-sub {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

/* ── 根部 ────────────────────────────────── */
.app-root {
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
}

/* 动态渐变背景 */
.bg-animated {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: var(--bg-page);
  transition: background var(--transition-slow);
}
.dark-mode .bg-animated {
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 35%, #0f2924 70%, #0f172a 100%);
  background-size: 400% 400%;
  animation: bgShift 20s ease infinite;
}
@keyframes bgShift {
  0%, 100% { background-position: 0% 50%; }
  50%      { background-position: 100% 50%; }
}

/* 应用容器 */
.app-shell {
  position: relative;
  z-index: 1;
  min-height: 100vh;
}

/* ── 头部 — 毛玻璃 ───────────────────────── */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 64px !important;
  padding: 0 28px;
  position: sticky;
  top: 0;
  z-index: 100;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-logo { font-size: 28px; animation: glowPulse 3s ease-in-out infinite; }
.header-title {
  font-size: 19px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.version-tag {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-primary-light);
  background: rgba(79, 70, 229, 0.12);
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 4px;
}
.header-right { display: flex; align-items: center; gap: 12px; }

/* 主题切换按钮 */
.theme-btn {
  background: transparent !important;
  border: 1px solid rgba(148, 163, 184, 0.3) !important;
  color: var(--text-secondary) !important;
  transition: all var(--transition-base) !important;
}
.theme-btn:hover {
  border-color: var(--color-primary-light) !important;
  color: var(--color-primary) !important;
  box-shadow: 0 0 12px rgba(79, 70, 229, 0.2) !important;
}

/* ── 主体 ────────────────────────────────── */
.app-main {
  padding: 20px 28px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.main-tabs {
  border-radius: var(--radius-xl) !important;
  overflow: hidden;
  box-shadow: var(--shadow-md);
}

.tab-label {
  font-size: 14px;
  font-weight: 500;
}

.tab-content {
  padding: 4px 0;
}

/* ── 空状态 ──────────────────────────────── */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-icon { font-size: 56px; margin-bottom: 16px; }
.empty-text {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.empty-sub {
  font-size: 13px;
  color: var(--text-muted);
}

/* ── 底部 ────────────────────────────────── */
.app-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 40px !important;
  padding: 0 28px;
}
.footer-text {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
}
.footer-quote {
  font-size: 12px;
  color: var(--text-secondary);
  font-style: italic;
  opacity: 0.8;
}
</style>
