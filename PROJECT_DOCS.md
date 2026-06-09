# 游戏包名爬虫系统 (Game Package Crawler) v2.8.1

> Android APK 版本排查工具 — FastAPI + Vue 3 前后端分离，5 大站点并发查询、版本对比、内置异步下载、Excel 批量处理。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术架构](#2-技术架构)
3. [目录结构](#3-目录结构)
4. [API 参考](#4-api-参考)
5. [数据源与爬虫](#5-数据源与爬虫)
6. [核心模块](#6-核心模块)
7. [前端组件](#7-前端组件)
8. [配置参考](#8-配置参考)
9. [安全特性](#9-安全特性)
10. [构建与部署](#10-构建与部署)
11. [版本历史](#11-版本历史)

---

## 1. 项目概述

### 1.1 用途

批量查询 Android APK 在各大应用商店的最新版本，与本地版本对比，判断是否需要更新。适用于游戏工作室、应用开发者、安全研究者。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 单包名查询 | 输入包名 → 秒级返回 5 个站点最新版本 |
| 批量 Excel 排查 | 上传 Excel → 并发查询 → 写回结果 |
| APK 下载 | 断点续传 + 浏览器回退绕过防盗链 |
| 版本记忆 | SQLite 持久化历史版本，减少重复查询 |
| 深色/浅色主题 | 自动跟随系统或手动切换 |
| 代理支持 | HTTP 代理配置，适配 GFW 环境 |

### 1.3 运行环境

- **OS**: Windows 10/11 (开发/打包), macOS/Linux (源码运行)
- **Python**: 3.10+
- **Node**: 18+ (前端构建)
- **Chromium**: Playwright headless shell (EXE 内置 ~264MB)

---

## 2. 技术架构

```
┌─────────────────────────────────────────────────┐
│                   桌面启动器                      │
│               launcher.py                        │
│   ┌──────────────┐   ┌──────────────────────┐   │
│   │  浏览器 Tab   │   │   uvicorn             │   │
│   │  (自动打开)   │   │   localhost:8000      │   │
│   └──────┬───────┘   └──────────┬───────────┘   │
└──────────┼──────────────────────┼───────────────┘
           │                      │
┌──────────▼──────────────────────▼───────────────┐
│              FastAPI 后端 (backend/)              │
│                                                  │
│  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ REST API │  │WebSocket │  │  Static Files  │  │
│  │ (routes) │  │  (ws)    │  │  (Vue3 dist)   │  │
│  └────┬─────┘  └────┬─────┘  └────────────────┘  │
│       │             │                             │
│  ┌────▼─────────────▼─────────────────────────┐  │
│  │              Orchestrator                    │  │
│  │   快源 (秒级)    │   慢源 (30-90s)           │  │
│  │   Google Play   │   APKMirror               │  │
│  │   APKPure       │   APKVision               │  │
│  │   APKCombo      │                            │  │
│  └────┬────────────┬───────────────────────────┘  │
│       │            │                               │
│  ┌────▼────┐  ┌───▼──────────────────────────┐   │
│  │ Fetcher │  │     StealthySession           │   │
│  │curl_cffi│  │  Chromium headless + CF绕过的 │   │
│  └─────────┘  └──────────────────────────────┘   │
│                                                   │
│  ┌─────────┐  ┌─────────┐  ┌──────────────────┐  │
│  │Download │  │  Batch  │  │  Cache (TTL)     │  │
│  │Manager  │  │ Manager │  │  + SlowTaskStore │  │
│  └─────────┘  └─────────┘  └──────────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────────┐ │
│  │  SQLite DB (data/crawler.db)                  │ │
│  │  user_history │ download_tasks │ batch_tasks │ │
│  └──────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────┘
```

### 2.1 HTTP 客户端三层架构

| 层级 | 函数 | 后端 | 速度 | 用途 |
|------|------|------|------|------|
| 1 | `http_get()` | Scrapling Fetcher (curl_cffi + browserforge) | 秒级 | 快源爬取 |
| 2 | `js_render_get()` | StealthySession (Chromium, CF=false) | ~10s | APKPure JS 渲染回退 |
| 3 | `stealth_get()` | StealthySession (Chromium, CF=true) | 30-90s | 慢源/CF 绕过 |

---

## 3. 目录结构

```
D:\game-package-crawler-proxy\
├── backend/                          # FastAPI 后端
│   ├── main.py                       # 应用入口、生命周期、中间件
│   ├── config.py                     # pydantic Settings + 热更新白名单
│   ├── logging_setup.py              # loguru 日志配置
│   │
│   ├── api/
│   │   ├── routes.py                 # 28 个 REST/WS 端点
│   │   └── websocket.py              # WebSocket 连接管理器
│   │
│   ├── scrapers/                     # 5 个站点爬虫
│   │   ├── base.py                   # BaseScraper 抽象基类
│   │   ├── google_play.py            # google-play-scraper 库
│   │   ├── apkpure.py                # Scrapling + JS 渲染回退
│   │   ├── apkcombo.py               # /api/app 302 重定向
│   │   ├── apkmirror.py              # Scrapling → Stealthy 回退
│   │   └── apkvision.py              # StealthySession 直接
│   │
│   ├── core/
│   │   ├── http_client.py            # 三层 HTTP + URL 安全验证
│   │   ├── parser.py                 # HTML 解析 (13 种 version_code 模式)
│   │   ├── version.py                # 版本号规范化与对比
│   │   ├── orchestrator.py           # 快/慢/全量查询调度器
│   │   ├── cache.py                  # TTL 内存缓存 + 慢任务存储
│   │   └── browser_manager.py        # Playwright 浏览器单例
│   │
│   ├── download/
│   │   ├── manager.py                # 异步下载 (aiohttp + 断点续传 + 浏览器回退)
│   │   └── extractors.py             # 下载链接提取器 (5 站)
│   │
│   ├── batch/
│   │   └── manager.py                # 批量任务 (Semaphore + Excel 写回)
│   │
│   ├── db/
│   │   └── database.py               # SQLite (WAL 模式, 3 张表)
│   │
│   ├── memo/
│   │   └── store.py                  # 版本记忆 CRUD
│   │
│   └── models/
│       └── schemas.py                # ApkInfo, FetchResult, DownloadTask
│
├── frontend/                         # Vue 3 + TypeScript + Element Plus
│   ├── index.html
│   ├── package.json                  # vue 3.5, element-plus 2.9, pinia 2.3
│   ├── vite.config.ts                # dev 代理配置
│   ├── tsconfig.json
│   ├── electron/
│   │   └── main.js                   # Electron 桌面壳
│   └── src/
│       ├── App.vue                   # 根组件 (加载屏 + 导航 + 底部)
│       ├── main.ts                   # Vue 入口
│       ├── stores/
│       │   └── app.ts                # Pinia 全局状态 + WS 连接
│       ├── components/
│       │   ├── PackageInput.vue      # 包名输入 + 模式选择
│       │   ├── ResultTable.vue       # 结果表格 + 版本对比
│       │   ├── BatchPanel.vue        # Excel 上传 + WS 进度
│       │   ├── DownloadQueue.vue     # 下载队列 + WS 实时更新
│       │   └── SettingsPanel.vue     # 全局设置面板
│       └── styles/
│           └── global.css            # CSS 变量 + 主题
│
├── tests/                            # 单元测试 (44 个用例)
│   ├── test_memo.py                  # 记忆化 CRUD
│   ├── test_parser.py                # HTML 解析 (12 模式)
│   └── test_version.py               # 版本对比逻辑
│
├── launcher.py                       # 桌面启动器
├── config.json                       # 用户配置文件
├── requirements.txt                  # Python 依赖
├── build.spec                        # PyInstaller 打包配置
├── build_exe.bat                     # 一键构建脚本
└── README.md                         # 入门文档
```

---

## 4. API 参考

### 4.1 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 基础健康检查 `{"status":"ok"}` |
| GET | `/api/ready` | 后端就绪状态 (含浏览器初始化) |
| POST | `/api/test-proxy` | 测试代理连通性，返回延迟 |

### 4.2 包名查询

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/fetch` | `{package, expected_version?, expected_version_code?, save_memo?}` | 快速排查 (等同于 /fetch/fast) |
| POST | `/api/fetch/fast` | 同上 | Google Play + APKPure + APKCombo (秒级) |
| POST | `/api/fetch/slow` | 同上 | APKMirror + APKVision (同步阻塞, 30-90s) |
| POST | `/api/fetch/slow/async` | 同上 | 慢源异步 → 返回 task_id |
| GET | `/api/fetch/slow/result/{task_id}` | — | 轮询异步任务结果 |
| POST | `/api/fetch/all` | 同上 | 全量 (所有已启用的站点) |
| POST | `/api/fetch/batch` | `{packages: [...], mode: "fast"}` | 多包名并发查询 (WebSocket 进度推送) |

### 4.3 批量 Excel

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/batch/upload` | 上传 .xlsx/.xls → 启动批量任务 (multipart) |
| GET | `/api/batch/{task_id}` | 查询任务状态 |
| POST | `/api/batch/{task_id}/pause` | 暂停 |
| POST | `/api/batch/{task_id}/resume` | 继续 |
| POST | `/api/batch/{task_id}/cancel` | 取消 |
| GET | `/api/batch/{task_id}/download` | 下载结果 Excel |

### 4.4 下载管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/download` | `{url, package, version?, arch?, detail_url?}` | 提交单个下载 |
| POST | `/api/download/batch` | `{items: [...]}` | 批量提交下载 |
| GET | `/api/download/tasks` | — | 获取所有下载任务状态 |
| POST | `/api/download/{id}/pause` | — | 暂停 |
| POST | `/api/download/{id}/resume` | — | 恢复 (v2.8.1) |
| POST | `/api/download/{id}/cancel` | — | 取消并删除 .part |

### 4.5 版本记忆

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memo` | 列出所有记忆 (limit=100) |
| GET | `/api/memo/{package_name}` | 查询单包名历史版本 |
| POST | `/api/memo` | `{package, version_code?, version_name?}` 保存 |

### 4.6 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 获取全部配置 |
| PATCH | `/api/config` | 更新配置 (仅白名单键, 敏感键拒绝) |

### 4.7 缓存与工具

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cache/clear` | 清除所有爬虫结果缓存 |
| POST | `/api/extract-links` | `{source, detail_url, package?, version?}` 提取下载直链 |

### 4.8 WebSocket

| 路径 | 说明 |
|------|------|
| `/api/ws` | 全局通道 — 下载进度 + 批量查询进度 |
| `/api/ws/{task_id}` | 任务通道 — 批量任务进度 |

**消息类型**:

| type | data | 方向 |
|------|------|------|
| `download_progress` | `{id, package_name, status, progress_pct, speed, ...}` | 后端→前端 |
| `batch_fetch_progress` | `{completed, total, progress_pct, mode}` | 后端→前端 |
| `batch_progress` | `{status, progress_pct, summary}` | 后端→前端 |
| `slow_task_completed` | `{task_id, status}` | 后端→前端 |

---

## 5. 数据源与爬虫

### 5.1 站点概览

| # | 站点 | 爬虫类 | 降级链 (v2.8.1) | 分类 | 代理 |
|---|------|--------|-------------------|------|------|
| 1 | Google Play | `GooglePlayScraper` | 库 → HTTP Fetcher | 快源 | ✅ |
| 2 | APKPure | `ApkpureScraper` | Fetcher → JS渲染 → .net → 详情页直连 | 快源 | ✅ |
| 3 | APKCombo | `ApkcomboScraper` | API → 详情页 → 搜索页 | 快源 | ✅ |
| 4 | APKMirror | `ApkmirrorScraper` | Fetcher → Stealthy → 搜索页提取 → 包名直连 | 慢源 | ✅ |
| 5 | APKVision | `ApkvisionScraper` | Fetcher → Stealthy + 详情页辅助 | 慢源 | — |

### 5.2 查询模式

| 模式 | 站点 | 响应时间 | API 端点 |
|------|------|----------|----------|
| 快速 (fast) | Google Play + APKPure + APKCombo | 1-5s | `/api/fetch` |
| 慢速 (slow) | APKMirror + APKVision | 30-90s | `/api/fetch/slow` |
| 慢速异步 | 同上 | 后台 | `/api/fetch/slow/async` |
| 全量 (all) | 全部已启用站点 | 混合 | `/api/fetch/all` |

### 5.3 爬虫基类

```python
class BaseScraper(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, package: str) -> ApkInfo:
        ...
```

所有爬虫继承 `BaseScraper` 并实现 `fetch()` 方法，返回 `ApkInfo` 数据类：

```python
@dataclass
class ApkInfo:
    source: str                # 来源名称
    package: str               # 包名
    version: str | None        # 版本名
    version_code: str | None   # 版本号 (3-12 位数字)
    detail_url: str | None     # 详情页 URL
    download_urls: list[str]   # 直链列表
    app_name: str | None       # 游戏中文名
    whats_new: str | None      # 更新内容
    error: str | None          # 错误信息
```

---

## 6. 核心模块

### 6.1 orchestrator.py — 查询调度器

```
query_fast(pkg, expected_v, expected_vc) → FetchResult
query_slow(pkg, expected_v, expected_vc) → FetchResult
query_single(pkg, expected_v, expected_vc) → FetchResult
query_batch(packages, mode, progress_callback, stop_event) → list[FetchResult]
```

- 每个模式独立 TTL 缓存
- `query_batch` 内部使用 `asyncio.Semaphore` 控制并发
- `_build_fetch_result()` 聚合多源结果 + 版本对比 + app_name/whats_new 优先级合并

### 6.2 http_client.py — HTTP 客户端

| 函数 | 后端 | 超时 | 并发模型 |
|------|------|------|----------|
| `http_get(url)` | Scrapling Fetcher | `request_timeout` | `asyncio.to_thread` |
| `stealth_get(url)` | StealthySession (CF) | `stealth_timeout+30s` | `threading.Thread`+ queue |
| `js_render_get(url)` | StealthySession (no CF) | 35s | `threading.Thread`+ queue |
| `validate_url(url, allow_all_https)` | DNS + IP 检查 | — | 同步 |

Fetcher 实例全局单例复用，避免重复握手。

### 6.3 parser.py — HTML 解析

**版本名提取**: 5 种策略 (class 选择器 → data-* 属性 → Schema.org itemprop → 全文正则 → 兜底)

**版本号提取**: 15 种正则模式，按特异性优先级匹配:
1. `data-dt-version_code` (APKPure 详情页, 限制包名 block 内)
2. `data-version_code` (通用, 带下划线变体)
3. `variant code:` (APKCombo 常见格式)
4. `x.y.z (code)` (括号形式, 版本号后直接跟 code)
5. `x.y.z <tag>(code)` (APKCombo blur span 格式, v2.8.1)
6. `x.y.z (code)` on stripped HTML (防 HTML 标签阻断, v2.8.1)
7. `data-dt-versioncode` (APKPure 搜索页, 连写无下划线)
8. `data-versioncode` (通用备选)
9. `<meta versionCode>` (HTML meta 标签)
10. JSON `"versionCode"` (嵌入式数据)
11. `Version Code:` 标签 (纯文本格式)
12. `data-app-versioncode` (备选 data 属性)
13. APK 文件名内嵌 code (`_12345_.apk`)
14. 定义列表 `<dt>/<dd>` (Version Code 键值对)
15. `version/ver/vc/code` 关键词兜底 (最低特异性)

### 6.4 download/manager.py — 下载管理器

```
DownloadManager
├── asyncio.Queue + Semaphore (并发控制)
├── aiohttp 流式下载 + Range 断点续传 (.part)
├── 0.5s 间隔速度计算 + WS 进度推送
├── SQLite 持久化任务状态
├── HTTP 403/404 → Playwright 浏览器下载回退
└── 启动时自动恢复未完成任务 (_resume_tasks)
```

### 6.5 batch/manager.py — 批量管理器

```
BatchManager
├── asyncio.Semaphore(batch_concurrency) 并发控制
├── asyncio.as_completed 实时跟踪进度
├── 暂停 (asyncio.sleep spin) / 恢复 / 取消
├── 结果流式写入 JSONL 临时文件 (低内存)
└── export_to_excel: 在原 Excel 插入 3 列 (排查时间/版本号/对比状态)
```

### 6.6 cache.py — 缓存

| 类 | 用途 | TTL |
|----|------|-----|
| `ScraperCache` | 爬虫结果缓存 `{pkg::mode → (FetchResult, expiry)}` | `cache_ttl_seconds` (默认 300s) |
| `SlowTaskStore` | 慢速异步任务存储 `{task_id → {status, result}}` | 3600s |

### 6.7 version.py — 版本对比

- `normalize(version)` — 去 v 前缀 + 统一分隔符
- `parse_version_tuple(version)` — 字符串 → 数值元组
- `compare_versions(a, b)` — 返回 1/0/-1
- `compare_version_codes(a, b)` — 数值比较
- `best_version(versions, google_version)` — 共识算法 (≥2 个源一致 / Google 优先)
- `best_version_code(codes)` — 取最大值
- `is_plausible_version(v)` — 过滤异常值 (年份/超长/纯数字)

---

## 7. 前端组件

### 7.1 组件树

```
App.vue
├── PackageInput.vue        — 包名输入 + 期望版本 + 模式选择 (快/慢/全)
├── ResultTable.vue         — 结果展示: 站点卡片 + 版本对比 + 下载按钮
├── BatchPanel.vue          — Excel 拖拽上传 + WS 进度条 + 暂停/继续/下载
├── DownloadQueue.vue       — 下载卡片列表 + 进度 + 暂停/恢复/删除
└── SettingsPanel.vue       — 主题开关 + 代理/并发/站点配置 + 记忆管理
```

### 7.2 Store (Pinia)

```typescript
// stores/app.ts — 全局状态
{
  // 主题
  darkMode, initDarkMode(), toggleDark(),

  // 查询
  loading, packageInput, expectedVersion, expectedVersionCode,
  fetchMode,  // 'fast' | 'slow' | 'all'
  results,    // FetchResult[]

  // 批量
  batchTaskId, batchProgress, batchTotal,

  // 下载
  downloadTasks,  // 通过 WS 实时更新

  // API
  apiBase,  // 'http://127.0.0.1:8000'

  // 方法
  doFetch(), doFetchBatch(), checkMemo(), saveMemo(),
  submitDownload(), refreshDownloads(), extractLinks(),
  connectGlobalWs(),  // 全局 WS (替代轮询)
}
```

### 7.3 WebSocket 数据流

```
App.vue onMounted
    └→ store.connectGlobalWs()
        └→ /api/ws (全局通道)
            ├→ download_progress → 更新 downloadTasks (实时)
            └→ batch_fetch_progress → 更新 batchProgress

BatchPanel 上传成功
    └→ connectWs(task_id)
        └→ /api/ws/{task_id} (任务通道)
            └→ batch_progress → 进度条 + 完成弹窗
                └→ 自动重连: 最多 5 次, 递增延迟 (2s→4s→...)
```

---

## 8. 配置参考

### 8.1 config.json

```json
{
  "download_path": "./downloads",
  "download_concurrency": 3,
  "download_chunk_size": 1048576,
  "scraper_concurrency": 4,
  "playwright_concurrency": 2,
  "batch_concurrency": 5,
  "cache_ttl_seconds": 300,
  "retry_times": 2,
  "retry_delay": 1.0,
  "proxy": "http://127.0.0.1:7897",
  "enabled_sites": [
    "google_play", "apkpure", "apkcombo", "apkmirror", "apkvision"
  ],
  "google_play_cookie_path": "",
  "log_level": "INFO",
  "log_retention_days": 30,
  "request_timeout": 10.0,
  "stealth_timeout": 60.0
}
```

### 8.2 热更新白名单 (可通过 PATCH /api/config 修改)

| 键 | 类型 | 说明 |
|----|------|------|
| `scraper_concurrency` | int (1-10) | 爬虫并发数 |
| `playwright_concurrency` | int (1-5) | Playwright 页面并发上限 |
| `batch_concurrency` | int (1-10) | 批量任务并发包名数 |
| `download_concurrency` | int (1-8) | 下载并发数 |
| `download_chunk_size` | int | 下载缓冲区 (字节) |
| `retry_times` | int (0-5) | 失败重试次数 |
| `retry_delay` | float | 重试间隔 (秒) |
| `cache_ttl_seconds` | int | 爬虫缓存 TTL |
| `request_timeout` | float | HTTP 请求超时 |
| `stealth_timeout` | float | 浏览器渲染超时 |
| `log_level` | "DEBUG"/"INFO"/"WARNING" | 日志级别 |
| `log_retention_days` | int | 日志保留天数 |
| `enabled_sites` | list[str] | 启用站点列表 |

### 8.3 敏感键 (需编辑 config.json 后重启)

| 键 | 说明 |
|----|------|
| `proxy` | HTTP 代理地址 |
| `download_path` | APK 下载目录 |
| `google_play_cookie_path` | Google Play Cookie 文件路径 |

---

## 9. 安全特性

### 9.1 SSRF 防护

`validate_url()` 函数在 `http_client.py` 中实现多层防御：

1. **协议检查**: 仅允许 http/https
2. **原始 IP 拒绝**: 直接拒绝数字 IP (回环/私有/链路本地/保留)
3. **DNS 解析后检查**: 解析域名 → 验证解析到的 IP 不是内部地址
4. **域名白名单**: 下载链接提取仅允许已知 APK CDN 域名
5. **下载 URL**: `allow_all_https=True` 放宽白名单，但仍拒绝私有 IP

### 9.2 路径遍历防护

`_safe_save_path()` 函数：
- 清理 `../` 路径段
- `Path.resolve()` 规范化后验证在 `download_path` 子树内

### 9.3 输入验证

- **包名**: 正则 `^[a-zA-Z][a-zA-Z0-9_.]{1,127}$` + 拒绝 `..`
- **配置热更新**: 白名单限制 + `extra="ignore"` 拒绝未知字段

### 9.4 CORS

仅允许 `127.0.0.1:8000`, `localhost:8000`, `127.0.0.1:5173`, `localhost:5173`。

### 9.5 速率限制 (v2.8.1)

slowapi 中间件全局限速 `60/minute`，敏感 POST 端点分级限流：

| 端点 | 限制 |
|------|------|
| `/api/fetch`, `/api/fetch/fast` | 30/min |
| `/api/fetch/slow`, `/api/fetch/slow/async`, `/api/fetch/all`, `/api/fetch/batch` | 10/min |
| `/api/download` | 20/min |
| `/api/download/batch`, `/api/extract-links` | 10-20/min |

### 9.6 WebSocket 来源验证 (v2.8.1)

WebSocket 连接验证 `Origin` 头，仅允许 localhost 和本地文件来源。

### 9.7 文件上传验证 (v2.8.1)

- 扩展名: 仅 `.xlsx` / `.xls`
- MIME 类型: 白名单检查
- 大小: 上限 50MB，下限 128 字节

---

## 10. 构建与部署

### 10.1 开发模式

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖 + 构建
cd frontend && npm install && npm run build && cd ..

# 启动
python launcher.py
# 或: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 10.2 打包 EXE

```bash
# 一键打包 (前端构建 + PyInstaller)
build_exe.bat

# 或手动步骤:
cd frontend && npm run build && cd ..
pyinstaller --clean --noconfirm build.spec
```

输出: `dist/游戏包名爬虫系统.exe` (~170MB，含 Chromium)

### 10.3 运行测试

```bash
pytest tests/ -v   # 44 个测试用例
```

### 10.4 依赖清单 (requirements.txt)

```
# Web Framework
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
websockets>=12.0
python-multipart>=0.0.9

# Async HTTP
aiohttp>=3.9.0
aiofiles>=24.0

# Scraping
scrapling[fetchers]>=0.4.0
beautifulsoup4>=4.12.0
curl_cffi>=0.15.0
google-play-scraper>=1.2.0

# Data & Config
pydantic>=2.0.0
pydantic-settings>=2.0.0
openpyxl>=3.1.0

# Version Comparison
packaging>=24.0

# Logging
loguru>=0.7.0

# Security
slowapi>=0.1.9

# Testing
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

---

## 11. 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v2.1 | 2025-05 | MVP: FastAPI + Vue3 基础架构, 5 站点爬虫 |
| v2.2 | 2025-05 | 记忆化输入、Excel 批量写回、下载队列 |
| v2.3 | 2025-05 | 设置面板、代理切换、站点开关 |
| v2.4 | 2025-06 | 批量并发 (Semaphore)、TTL 缓存、慢源异步、流式 Excel |
| v2.5 | 2025-06 | 深色/浅色主题、Cloudflare 检测增强、app_name/whats_new |
| v2.6 | 2025-06 | BatchPanel 重构、DownloadQueue 独立组件 |
| v2.7 | 2025-06 | SettingsPanel 重做、配置热更新 |
| v2.8 | 2025-06 | 全局 CSS 主题变量、UI 一致性优化、启动器完善 |
| **v2.8.1** | **2025-06** | **安全加固 + Bug 修复 + 死代码清理 (本次审计)** |

### v2.8.1 变更详情 (2025-06-08 ~ 2025-06-09)

**Bug 修复 (9 项)**:
| 修复 | 说明 |
|------|------|
| 主题开关弹回 | `v-model` → `:model-value`, 消除与 `@change` 冲突 |
| 重复 onMounted | App.vue 合并两个重复初始化块 |
| 测试代理无效 | 新增 `POST /api/test-proxy` 端点, 返回延迟 |
| 按钮标签误导 | "恢复默认" → "重新加载" |
| 下载无恢复按钮 | 新增 `resume_task` + `POST /api/download/{id}/resume` |
| 爬虫 Cookie 失效 | Google Play `cookie_data` 传递给 `gp_app()` |
| APKCombo vc 缺失 | parser 新增 2b/2c 模式, vc 全源覆盖 |
| validate_url IP 检查 | 修复 `except ValueError: pass` 吞掉拒绝逻辑 |
| Excel 列顺序错乱 | 先插入列后写标题 + 最终排序 |

**安全加固 (10 项)**:
| 修复 | 说明 |
|------|------|
| SSRF 防护 | `validate_url()` — DNS 解析后 IP 检查 + 域名白名单 |
| 路径遍历防护 | `_validate_package_name()` + `_safe_save_path()` |
| CORS 收紧 | `allow_origins` 限定 localhost 来源 |
| 配置热更新白名单 | 敏感键 (`proxy`/`download_path`/`cookie_path`) 拒绝 API 修改 |
| `extra="ignore"` | 拒绝未知配置键, 防止拼写错误 |
| 速率限制 | slowapi — 全局限速 60/min, POST 端点分级 |
| WS 来源验证 | `/ws` 端点验证 `Origin` 头 |
| 文件上传验证 | MIME 白名单 + 50MB 上限 + 最小 128B |
| 输入验证 | 包名正则 `^[a-zA-Z][a-zA-Z0-9_.]{1,127}$` |
| URL 验证应用 | `/api/download`, `/api/extract-links` 应用 SSRF 防护 |

**爬虫健壮性 (5 项)**:
| 爬虫 | 改进 |
|------|------|
| Google Play | Cookie 修复 + 库不可用时 HTTP 降级 |
| APKPure | 多模式 URL 提取 (双引号/单引号/相对路径/多域名) + 详情页直连兜底 |
| APKCombo | `/api/app` → 详情页 → 搜索页三级降级 |
| APKMirror | 4 种正则模式 + 包名直连兜底 + 搜索页直接提取 |
| APKVision | Fetcher 优先 → Stealthy 降级 + 详情页辅助提取 |

**代码清理 (8 项)**:
- 删除 `useWebSocket.ts`、`selectors.yaml`、`extractors.py` 4 个死函数
- 移除 `sourceStatus` 计算属性、未使用 imports (`os`/`DownloadManager`/`BackgroundTasks`/`urlparse`)
- 移除 `sqlalchemy`/`aiosqlite`/`pyyaml` 依赖
- 移除未使用配置键 (`request_interval`/`auto_cleanup_days`/`language`)
- import 提升至模块级 (`unescape`/`datetime`) + 移除冗余局部 import (8 处)
- 正则规范: `[\d]` → `\d`

**功能改进 (4 项)**:
- 全局 WebSocket 替代下载队列轮询
- `/api/fetch/batch` 接入 WS 进度推送
- BatchPanel WS 自动重连 (5 次递增延迟)
- 配置热更新白名单

---

> **作者**: ALwinrk | **仓库**: `D:\game-package-crawler-proxy` | **旧版 gvc v5**: `D:\Project_game-version-check`
