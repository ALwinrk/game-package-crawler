# 游戏包名爬虫系统 v3.7

Android APK 版本排查工具 — FastAPI + Vue 3 前后端分离架构。支持 6 大站点/数据源并发查询、实时更新游戏面板（APKPure/APKCombo/APKVision）、版本对比、内置异步下载（断点续传+重试+架构识别）、Excel 批量处理、记忆化输入、动态系统公告。

## 目录结构

```
├── backend/                 # FastAPI 后端
│   ├── main.py              # FastAPI 入口 + lifespan 管理 + 启动优化
│   ├── config.py            # pydantic-settings 配置管理 + 热更新白名单
│   ├── logging_setup.py     # loguru 日志配置
│   ├── api/                 # REST + WebSocket 路由
│   │   ├── routes.py        # 31 个 REST API 端点
│   │   └── websocket.py     # WebSocket 进度推送
│   ├── models/              # 数据模型 (dataclass + Enum)
│   │   └── schemas.py
│   ├── scrapers/            # 5 个站点爬虫
│   │   ├── base.py          # 爬虫抽象基类
│   │   ├── google_play.py   # 双语言查询 + HTTP 降级
│   │   ├── apkpure.py       # 搜索→详情两步提取 + JS 渲染降级
│   │   ├── apkcombo.py      # API→搜索页三层兜底
│   │   ├── apkmirror.py     # 搜索→详情→下载多步跳转
│   │   └── apkvision.py     # Fetcher→StealthySession 双重降级
│   ├── core/                # 核心库
│   │   ├── http_client.py   # HTTP 客户端 (Fetcher/StealthySession/JS渲染 三层后端)
│   │   ├── parser.py        # HTML 解析：版本号 + version code 15 模式提取
│   │   ├── version.py       # 版本号标准化 + 比较 + 最优判定
│   │   ├── orchestrator.py  # 查询调度器 (快/慢源编排 + 重试 + 缓存)
│   │   ├── cache.py         # TTL 内存缓存 + 慢任务异步存储
│   │   └── browser_manager.py # Playwright 持久化浏览器池 (信号量限流)
│   ├── download/            # 异步下载管理器
│   │   ├── manager.py       # 队列+进度+断点续传+重试+架构识别+浏览器下载
│   │   └── extractors.py    # 下载链接提取器 (APKPure/APKCombo/APKMirror/APKVision)
│   ├── batch/               # Excel 批量任务管理器
│   │   └── manager.py       # 流式结果写入 + Semaphore 并发控制
│   ├── cron/                # 定时任务
│   │   └── update_tracker.py # APKPure/APKCombo/APKVision 实时面板 + 熔断器
│   ├── db/                  # SQLite 数据库
│   │   └── database.py      # 线程安全连接池 + 自动重连
│   └── memo/                # 记忆化输入存储
│       └── store.py
├── frontend/                # Vue 3 + TypeScript + Element Plus
│   ├── index.html
│   ├── src/
│   │   ├── App.vue          # 主布局 (深色/浅色主题 + 启动加载屏)
│   │   ├── main.ts          # Vue 入口
│   │   ├── stores/          # Pinia 状态管理
│   │   │   └── app.ts
│   │   ├── components/
│   │   │   ├── PackageInput.vue     # 包名输入 + 快/慢/全量模式选择
│   │   │   ├── ResultTable.vue      # 结果展示 + 游戏信息卡片 + 版本对比
│   │   │   ├── BatchPanel.vue       # Excel 批量排查面板
│   │   │   ├── DownloadQueue.vue    # 下载队列管理 (含架构标签)
│   │   │   ├── DailyUpdates.vue     # 实时更新游戏面板 (含右键复制)
│   │   │   └── SettingsPanel.vue    # 设置面板 (代理/并发/站点开关)
│   │   └── styles/
│   │       └── global.css           # 全局样式 + 暗色/亮色主题变量
├── tests/                   # 单元测试 (44 条, pytest)
│   ├── test_parser.py       # HTML 解析器测试
│   ├── test_version.py      # 版本比较测试
│   └── test_memo.py         # 记忆化存储测试
├── launcher.py              # 桌面启动器 (一键启动后端+浏览器, 数据持久化)
├── config.json              # 用户配置 (代理/并发/站点开关等)
├── requirements.txt         # Python 依赖
├── build.spec               # PyInstaller 打包配置
├── build_exe.bat            # 一键构建 EXE
├── deploy_server.bat        # 云服务器部署脚本 (防火墙+开机自启)
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置代理 (可选)

编辑 `config.json`，将 `proxy` 改为你的代理地址：

```json
"proxy": "http://127.0.0.1:7892"
```

留空字符串 `""` 表示不使用代理。

### 3. 启动 (三种方式)

**方式 A — 桌面启动器 (推荐，一键启动)**

```bash
python launcher.py
```

→ 自动打开浏览器，切换到数据目录，注册退出处理。

**方式 B — 命令行启动后端**

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**方式 C — 直接运行**

```bash
python backend/main.py
```

### 4. 打开前端

浏览器访问: http://127.0.0.1:8000

首次启动面板无数据，需手动点击「🔄 全量刷新」开始爬取。之后每小时自动增量更新。

### 5. API 文档

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## 全部 API 端点

### 健康检查 & 配置

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/ready` | GET | 后端就绪检查 (浏览器引擎是否启动) |
| `/api/config` | GET | 获取当前配置 |
| `/api/config` | PATCH | 热更新配置 (仅白名单字段) |
| `/api/test-proxy` | POST | 测试代理连通性 |
| `/api/cache/clear` | POST | 清除爬虫结果缓存 |

### 包名排查 (三级模式)

| 端点 | 方法 | 限速 | 说明 |
|------|------|------|------|
| `/api/fetch` | POST | 30/min | 单包名查询，默认快速模式 |
| `/api/fetch/fast` | POST | 30/min | 快速排查 — Google Play + APKPure + APKCombo（秒级） |
| `/api/fetch/slow` | POST | 10/min | 慢速排查 — APKMirror + APKVision（30-90s，同步阻塞） |
| `/api/fetch/slow/async` | POST | 10/min | 慢速异步提交 — 立即返回 task_id |
| `/api/fetch/slow/result/{task_id}` | GET | - | 轮询慢速异步结果 |
| `/api/fetch/all` | POST | 10/min | 全量排查 — 全部启用站点 |
| `/api/fetch/batch` | POST | 10/min | 多包名并发查询 |

### Excel 批量处理

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/batch/upload` | POST | 上传 Excel，自动识别列，启动批量排查 |
| `/api/batch/{task_id}` | GET | 查询批量任务状态与进度 |
| `/api/batch/{task_id}/pause` | POST | 暂停批量任务 |
| `/api/batch/{task_id}/resume` | POST | 恢复批量任务 |
| `/api/batch/{task_id}/cancel` | POST | 取消批量任务 |
| `/api/batch/{task_id}/download` | GET | 下载排查结果 Excel |

### 下载管理

| 端点 | 方法 | 限速 | 说明 |
|------|------|------|------|
| `/api/download` | POST | 20/min | 提交单个下载任务 |
| `/api/download/batch` | POST | 10/min | 批量提交下载任务 |
| `/api/download/tasks` | GET | - | 获取所有下载任务状态 |
| `/api/download/{task_id}/pause` | POST | - | 暂停下载 |
| `/api/download/{task_id}/resume` | POST | - | 恢复暂停的下载 |
| `/api/download/{task_id}/cancel` | POST | - | 取消下载 (删除 .part 文件) |
| `/api/extract-links` | POST | 20/min | 从详情页提取下载直链 (含架构识别) |

### 实时更新面板

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/daily-updates` | GET | 获取 APKPure/APKCombo/APKVision 最近更新 (支持 304 条件请求) |
| `/api/daily-updates/refresh` | POST | v3.5 fire-and-forget 全量刷新 (立即返回, 后台执行) |
| `/api/daily-updates/refresh-incremental` | POST | v3.5 fire-and-forget 增量刷新 (立即返回, 后台执行) |
| `/api/daily-updates/refresh-status` | GET | 查询刷新任务是否正在运行 |

### 记忆化 & WebSocket

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/memo/{package_name}` | GET | 查询包名历史版本 |
| `/api/memo` | POST | 保存版本信息到记忆 |
| `/api/memo` | GET | 列出所有记忆 (最近 100 条) |
| `/api/ws` | WS | 全局 WebSocket — 下载进度 + 批量通知 |
| `/api/ws/{task_id}` | WS | 任务 WebSocket — 订阅特定任务进度 |

## 配置

编辑 `config.json`（运行时可通过 Settings 面板或 PATCH `/api/config` 修改白名单字段）：

```json
{
  "download_path": "./downloads",
  "download_concurrency": 3,
  "download_chunk_size": 1048576,
  "scraper_concurrency": 6,
  "playwright_concurrency": 2,
  "batch_concurrency": 5,
  "cache_ttl_seconds": 300,
  "retry_times": 2,
  "retry_delay": 1.0,
  "request_timeout": 10.0,
  "stealth_timeout": 30.0,
  "proxy": "http://127.0.0.1:7897",
  "enabled_sites": ["google_play", "apkpure", "apkcombo", "apkmirror", "apkvision"],
  "google_play_cookie_path": "",
  "update_check_interval": 1800,
  "daily_updates_pages": 3,
  "daily_updates_limit": 100,
  "frontend_poll_interval": 300,
  "panel_max_items": 300,
  "apkpure_display_limit": 90,
  "apkcombo_display_limit": 60,
  "apkcombo_trending_display_limit": 90,
  "apkvision_display_limit": 40,
  "apkvision_new_display_limit": 40,
  "notice_enabled": false,
  "notice_text": "",
  "log_level": "INFO",
  "log_retention_days": 30
}
```

| 字段 | 类型 | 默认值 | 热更新 | 说明 |
|------|------|--------|--------|------|
| `download_path` | str | `./downloads` | ❌ | APK 下载目录，需重启生效 |
| `download_concurrency` | int | 3 | ✅ | 同时下载任务数 |
| `download_chunk_size` | int | 1048576 | ✅ | 下载缓冲区大小 (1MB) |
| `scraper_concurrency` | int | 6 | ✅ | 爬虫同时请求数 |
| `playwright_concurrency` | int | 2 | ✅ | Playwright 浏览器并发页面上限 |
| `batch_concurrency` | int | 5 | ✅ | 批量任务同时处理包名数 |
| `cache_ttl_seconds` | int | 300 | ✅ | 爬虫结果缓存有效期 (5分钟) |
| `retry_times` | int | 2 | ✅ | 爬虫失败重试次数 |
| `retry_delay` | float | 1.0 | ✅ | 重试间隔 (秒) |
| `request_timeout` | float | 10.0 | ✅ | HTTP 请求超时 (秒) |
| `stealth_timeout` | float | 30.0 | ✅ | StealthySession 浏览器超时 (秒), v3.5 降低 |
| `proxy` | str | `http://127.0.0.1:7897` | ✅ | HTTP/HTTPS 代理地址 |
| `enabled_sites` | list | 5 站点全部启用 | ✅ | 启用的爬虫站点 |
| `google_play_cookie_path` | str | `""` | ❌ | Google Play Cookie 文件路径，需重启生效 |
| `update_check_interval` | int | 1800 | ✅ | 定时抓取间隔 (30分钟) |
| `daily_updates_pages` | int | 3 | ✅ | 每个源抓取页数 |
| `daily_updates_limit` | int | 100 | ✅ | API 默认返回条数 |
| `frontend_poll_interval` | int | 300 | ✅ | 前端轮询间隔 (5分钟) |
| `panel_max_items` | int | 300 | ✅ | 每源数据库保留上限 |
| `apkpure_display_limit` | int | 90 | ✅ | APKPure 面板展示条数 |
| `apkcombo_display_limit` | int | 60 | ✅ | APKCombo 面板展示条数 |
| `apkcombo_trending_display_limit` | int | 90 | ✅ | APKCombo Trending 展示条数 |
| `apkvision_display_limit` | int | 40 | ✅ | APKVision Updated 展示条数 |
| `apkvision_new_display_limit` | int | 40 | ✅ | APKVision New 展示条数 |
| `notice_enabled` | bool | false | ✅ | 系统公告开关（v3.6） |
| `notice_text` | str | `""` | ✅ | 公告内容，支持 HTML（v3.6） |
| `log_level` | str | `INFO` | ✅ | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `log_retention_days` | int | 30 | ✅ | 日志保留天数 |

> **注意**: `download_path` 和 `google_play_cookie_path` 属于敏感配置，热更新会被静默跳过，需手动编辑 `config.json` 后重启。

## 支持的站点

| 站点 | 类型 | 后端 | 代理 | 说明 |
|------|------|------|------|------|
| Google Play | 🔵 快速源 | google-play-scraper + HTTP 降级 | 需要 | 最权威来源，双语言查询 |
| APKPure | 🔵 快速源 | Scrapling + JS 渲染降级 | 需要 | 绕过 Cloudflare，中文站详情页 |
| APKCombo | 🔵 快速源 | Scrapling (/api/app + 搜索页) | 需要 | 三层兜底策略 |
| APKMirror | 🟡 慢速源 | Scrapling + StealthySession | 需要 | 多步跳转详情页 |
| APKVision | 🟡 慢速源 | StealthySession | 不需要 | CF JS Challenge，支持实时更新面板 |

### 实时更新面板数据源

| 源标识 | 内容 | 说明 |
|--------|------|------|
| `apkpure` | APKPure 排名页 | 10 个游戏分类，跨分类去重 + 关键词黑名单过滤 |
| `apkcombo` | APKCombo 热门游戏 | 按下载量排序，关键词黑名单过滤 |
| `apkcombo_trending` | APKCombo 最新更新 | 最近更新游戏，关键词黑名单过滤 |
| `apkvision_updated` | APKVision 最近更新 | 20 条，含详情页时间 |
| `apkvision_new` | APKVision 新游戏 | 20 条，含详情页时间 |

## 运行测试

```bash
pytest tests/ -v
```

44 条测试覆盖：版本解析、版本比较、HTML 解析、记忆化存储。

## 打包为 EXE

```bash
build_exe.bat
```

→ 输出: `dist/游戏包名爬虫系统.exe` (~264MB，含 Chromium headless shell)

### 构建前置条件

1. Python 3.11+ 并安装全部依赖
2. Playwright Chromium 已安装: `playwright install chromium`
3. EXE 首次运行会自动复制预置 `config.json` 到 EXE 所在目录

## 云服务器部署

适用于腾讯云/阿里云 Windows 服务器，供团队共用：

1. **远程桌面**连接服务器，将 `dist/游戏包名爬虫系统.exe` 和 `deploy_server.bat` 复制到服务器
2. 右键 `deploy_server.bat` → **以管理员身份运行**（自动配置防火墙 + 开机自启 + 启动服务）
3. 进云控制台 → 安全组 → 添加入站规则：`TCP 8000` 允许 `0.0.0.0/0`
4. 团队成员浏览器访问 `http://服务器IP:8000`

更新代码时只需覆盖 EXE 并重启进程，无需重新运行部署脚本。

## 版本历史

| 版本 | 主要变更 |
|------|----------|
| v2.1 | MVP: FastAPI + Vue3 基础架构, 5 站点爬虫 |
| v2.2 | 记忆化输入、Excel 批量写回、下载队列 |
| v2.3 | 设置面板、代理切换、站点开关 |
| v2.4 | 批量并发 (Semaphore)、TTL 缓存、慢源异步、流式 Excel |
| v2.5 | 深色/浅色主题、游戏中文名+更新内容卡片、Cloudflare 检测增强 |
| v2.6 | BatchPanel 重构、DownloadQueue 独立组件 |
| v2.7 | SettingsPanel 重做、配置热更新白名单 |
| v2.8 | 全局 CSS 主题变量、UI 一致性优化、启动器完善、中文详情页 |
| v3.0 | 实时更新游戏面板（APKPure/APKCombo）、下载重试+HEAD预检+架构识别、APKCombo分类过滤、三列分栏布局、独立标签页、速率限制(slowapi)、日志系统(loguru) |
| v3.1 | APKVision 实时更新面板、代理降级直连修复（空 dict vs None）、配置热更新原子性修复、前端 resp.ok 检查 |
| v3.2 | **启动优化**: DB 缓存预热，有数据立即可用。**EXE 数据持久化**: 工作目录改为 EXE 所在目录。**配置安全**: 热更新白名单移除敏感字段 + 数值类型校验。**手动刷新**: 触发实际爬取并等待完成。**APKPure 优化**: 分类砍半 + stealth 降级 + 批次间暂停。**UI**: 右键复制包名、实时面板置顶。**前端**: 所有 fetch 增加 resp.ok 检查 + catch 块日志 |
| v3.3 | **反封禁**: TLS 指纹轮换 (5 指纹池) + 分类随机顺序 + 间隔随机化 3-7s。**Chromium 持久化**: 复制到 EXE 目录防杀软拦截，启动零 EPIPE。**浏览器反检测**: AutomationControlled + 随机 viewport + stealth 脚本。**熔断增强**: API 手工重置 + 连续失败自动降频至 7200s。**下载修复**: APKCombo/APKPure URL 双语言码修复 + HTML 页面自动降级 Playwright + JS 触发带 Referer 下载。**UI**: 结果表格三按钮 (详情页/浏览器下载/点击下载) |
| v3.4 | **增量更新**: Top-N 增量+提前终止算法, 定时更新请求量 -83%。**入库去重**: (source,package) 唯一索引 + INSERT OR REPLACE 合并。**容量控制**: 数据库 150/面板 90-90-60 分源可配。**双刷新模式**: 全量/增量按钮 + 刷新面板按钮。**首次全量**: full_refresh 标志跳过提前终止。**服务器部署**: ms-playwright Chromium 兜底。**EXE 稳定性**: 全局异常捕获 + 端口占用检查 + 版本号统一 v3.4 |
| v3.5 | **CF 防护**: StealthySession 子类限制 CF 求解递归 (_MAX_CF_SOLVE_ATTEMPTS=2), 防止 interactive Turnstile 无限循环。**域名切换**: APKPure 主域名 apkpure.com → apkpure.net (Fetcher 可用)。**CF 感知熔断**: record_cf_failure 2× 权重加速降频/熔断。**面板调整**: 各源独立展示上限 (90/60/90/40/40)。**刷新改版**: fire-and-forget 模式，点击立即返回，后台执行 + 前端自动轮询，彻底解决超时等待。**超时优化**: stealth_timeout 45→30s |
| v3.6 | **APKPure 关键词过滤**...启动行为: 不再自动全量刷新，需手动点击「全量刷新」触发爬取。 |
| v3.7 | **数据源选择器**: 面板新增📡下拉多选框，按需选择刷新指定源，避免全量爬取；per-source 锁定允许不同源并行刷新。**启动优化**: launcher 端口等待(3s延迟+30s超时)消除 ERR_CONNECTION_REFUSED；前端弹性轮询(指数退避+60s超时)；浏览器初始化失败不再阻塞就绪；移除 lifespan 45s 空等待。**增量提速**: APKCombo 详情富化上限缩减(60→30, 90→40)，单次增量周期加速~50%。**APKCombo 日期修复**: `.ver-item` 选择器多备选兜底 + `_parse_iso_date` 支持 ISO/英文月份格式。**公告编辑修复**: 公告卡片独立保存按钮。**关键词黑名单扩展**: 新增棋牌/博彩/斗地主等中文关键词。 |

详见: `版本总历史.md`、`系统工作流程\系统工作流程.md

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + uvicorn |
| 爬虫引擎 | Scrapling (Fetcher / StealthySession) + curl_cffi + google-play-scraper |
| 浏览器 | Playwright (patchright) — 持久化 Chromium 上下文 |
| 数据库 | SQLite (WAL 模式, 线程安全) |
| 前端 | Vue 3 + TypeScript + Element Plus + Pinia |
| 打包 | PyInstaller (含 Chromium headless shell) |
| 日志 | loguru |
| 测试 | pytest |

## 从旧版 (gvc v5) 迁移

旧版项目：`D:\Project_game-version-check` (CustomTkinter GUI, 单进程 Python)

本版本复用旧版核心代码：
- `gvc/parser.py` → `backend/core/parser.py` (90% 复用)
- `gvc/version.py` → `backend/core/version.py` (70% 复用，增强)
- `gvc/http_client.py` → `backend/core/http_client.py` (80% 复用)
- `gvc/sources.py` → `backend/scrapers/*.py` (50-65% 复用)
- `gvc/downloader.py` → `backend/download/extractors.py` (70% 复用)
