# 游戏包名爬虫系统 v3.0

Android APK 版本排查工具 — FastAPI + Vue 3 前后端分离架构。支持 5 大站点并发查询、实时更新游戏面板（APKPure/APKCombo）、版本对比、内置异步下载（断点续传+重试+架构识别）、Excel 批量处理、记忆化输入。

## 目录结构

```
D:\game-package-crawler-proxy\
├── backend/                 # FastAPI 后端
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # pydantic 配置
│   ├── api/                 # REST + WebSocket 路由
│   │   └── routes.py
│   ├── models/              # 数据模型 (Pydantic schemas)
│   │   └── schemas.py
│   ├── scrapers/            # 5 个站点爬虫
│   │   ├── google_play.py
│   │   ├── apkpure.py
│   │   ├── apkcombo.py
│   │   ├── apkmirror.py
│   │   └── apkvision.py
│   ├── core/                # 核心库
│   │   ├── http_client.py   # HTTP 客户端 (Scrapling + curl_cffi)
│   │   ├── parser.py        # HTML/JSON 解析
│   │   ├── version.py       # 版本号提取与规范化
│   │   ├── orchestrator.py  # 查询调度器 (快/慢源编排)
│   │   └── cache.py         # TTL 爬虫缓存 + 慢任务存储
│   ├── download/            # 异步下载管理器
│   │   ├── manager.py       # 下载队列+进度+重试+架构识别
│   │   └── extractors.py    # URL 提取器
│   ├── batch/               # 批量任务管理器
│   │   └── manager.py       # 批量并发 (Semaphore 控制)
│   ├── cron/                # 定时任务
│   │   └── update_tracker.py # 实时更新游戏面板抓取
│   └── db/                  # SQLite 数据库 + 记忆化
├── frontend/                # Vue 3 + TypeScript + Element Plus
│   ├── index.html
│   ├── src/
│   │   ├── App.vue          # 主布局 (深色/浅色主题)
│   │   ├── main.ts          # Vue 入口
│   │   ├── stores/          # Pinia 状态管理
│   │   │   └── app.ts
│   │   ├── components/
│   │   │   ├── PackageInput.vue     # 包名输入与快/慢查询
│   │   │   ├── ResultTable.vue      # 结果展示表格
│   │   │   ├── BatchPanel.vue       # Excel 批量面板
│   │   │   ├── DownloadQueue.vue    # 下载队列管理 (含架构标签)
│   │   │   ├── DailyUpdates.vue     # 实时更新游戏面板
│   │   │   └── SettingsPanel.vue    # 设置面板 (代理/并发/站点)
│   │   └── styles/
│   │       └── global.css           # 全局样式 + 主题变量
│   └── package.json (由 Electron/build 脚本管理)
├── tests/                   # 单元测试
├── launcher.py              # 桌面启动器 (一键启动后端+浏览器)
├── config.json              # 用户配置
├── requirements.txt         # Python 依赖
├── build.spec               # PyInstaller 打包配置
├── build_exe.bat            # 构建脚本
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 (三种方式)

**方式 A — 桌面启动器 (推荐，一键启动)**

```bash
python launcher.py
```

**方式 B — 命令行启动后端**

```bash
cd D:\game-package-crawler-proxy
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**方式 C — 直接运行**

```bash
python backend/main.py
```

### 3. 打开前端

浏览器访问: http://127.0.0.1:8000

### 4. API 文档

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## 主要 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/fetch` | POST | 单包名查询 (快/慢源) |
| `/api/fetch/batch` | POST | 多包名并发查询 |
| `/api/fetch/slow/async` | POST | 慢源异步查询 (返回 task_id) |
| `/api/fetch/slow/result/{task_id}` | GET | 轮询慢源结果 |
| `/api/batch/upload` | POST | 上传 Excel 批量排查 |
| `/api/download` | POST | 提交 APK 下载任务 |
| `/api/daily-updates` | GET | 实时更新游戏面板 |
| `/api/cache/clear` | POST | 清除爬虫缓存 |
| `/api/memo/{pkg}` | GET | 查询记忆化版本 |
| `/api/config` | GET/PATCH | 配置管理 |
| `/api/ws` | WS | 全局进度推送 |
| `/api/ws/{task_id}` | WS | 任务进度推送 |

## 配置

编辑 `config.json`：

```json
{
  "download_path": "./downloads",
  "scraper_concurrency": 4,
  "batch_concurrency": 5,
  "download_concurrency": 3,
  "cache_ttl_seconds": 300,
  "download_chunk_size": 1048576,
  "proxy": "http://127.0.0.1:7897",
  "enabled_sites": ["google_play", "apkpure", "apkcombo", "apkmirror", "apkvision"],
  "retry_times": 2,
  "language": "zh"
}
```

## 支持的站点

| 站点 | 后端 | 代理 | 说明 |
|------|------|------|------|
| Google Play | google-play-scraper | 需要 | 最权威来源 |
| APKPure | Scrapling + JS 渲染 | 需要 | 绕过 Cloudflare |
| APKCombo | Scrapling | 需要 | /api/app 302 跳转 |
| APKMirror | Scrapling + Stealthy | 需要 | 多步跳转 |
| APKVision | StealthySession | 不需要 | CF JS Challenge |

## 运行测试

```bash
pytest tests/ -v
```

## 打包为 EXE

```bash
build_exe.bat
```

→ 输出: `dist/游戏包名爬虫系统.exe`

要求 Python 3.11+，所有依赖已安装，Chromium headless shell 随包打包 (~264MB)。

## 云服务器部署

适用于腾讯云/阿里云 Windows 服务器，供团队共用：

1. **远程桌面**连接服务器，将 `dist/游戏包名爬虫系统.exe` 和 `deploy_server.bat` 拖入
2. 右键 `deploy_server.bat` → **以管理员身份运行**（自动配置防火墙 + 开机自启 + 启动服务）
3. 进云控制台 → 安全组 → 添加入站规则：`TCP 8000` 允许 `0.0.0.0/0`
4. 同事浏览器访问 `http://服务器IP:8000`

更新代码时只需覆盖 exe 并重启，无需重新运行部署脚本。

## 版本历史

| 版本 | 主要变更 |
|------|----------|
| v2.1 | MVP: FastAPI + Vue3 基础架构, 5 站点爬虫 |
| v2.2 | 记忆化输入、Excel 批量写回、下载队列 |
| v2.3 | 设置面板、代理切换、站点开关 |
| v2.4 | 批量并发 (Semaphore)、TTL 缓存、慢源异步、流式 Excel |
| v2.5 | 深色/浅色主题、Cloudflare 检测增强 |
| v2.6 | BatchPanel 重构、DownloadQueue 独立组件 |
| v2.7 | SettingsPanel 重做、配置热更新 |
| v2.8 | 全局 CSS 主题变量、UI 一致性优化、启动器完善 |
| v3.0 | 实时更新游戏面板（APKPure/APKCombo）、下载重试+HEAD预检+架构识别、APKCombo分类过滤+50K+源、APKPure版本名提取、三列分栏布局、每日更新独立标签页 |

详见: `版本总历史.md`、`系统工作流程\系统工作流程.md`

## 从旧版 (gvc v5) 迁移

旧版项目：`D:\Project_game-version-check` (CustomTkinter GUI, 单进程 Python)

本版本复用旧版核心代码：
- `gvc/parser.py` → `backend/core/parser.py` (90% 复用)
- `gvc/version.py` → `backend/core/version.py` (70% 复用，增强)
- `gvc/http_client.py` → `backend/core/http_client.py` (80% 复用)
- `gvc/sources.py` → `backend/scrapers/*.py` (50-65% 复用)
- `gvc/downloader.py` → `backend/download/extractors.py` (70% 复用)
