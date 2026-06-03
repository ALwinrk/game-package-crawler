# 游戏包名爬虫系统

Android APK 版本排查工具 — 前后端分离架构，支持 5 大站点并发查询、版本对比、内置异步下载（断点续传）、Excel 批量处理、记忆化输入。

## 目录结构

```
C:\new_version\
├── backend/             # FastAPI 后端
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # pydantic 配置
│   ├── api/             # REST + WebSocket
│   ├── models/          # 数据模型
│   ├── scrapers/        # 5 个站点爬虫 + selectors.yaml
│   ├── core/            # 核心库 (HTTP/解析/版本/调度)
│   ├── download/        # 异步下载管理器
│   ├── batch/           # 批量任务管理器
│   ├── memo/            # 记忆化存储
│   └── db/              # SQLite 数据库
├── tests/               # 单元测试
├── config.json          # 用户配置
├── requirements.txt     # Python 依赖
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动后端

```bash
cd C:\new_version
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

或直接运行：

```bash
python backend/main.py
```

### 3. 验证

```bash
curl http://127.0.0.1:8000/api/health
```

### 4. API 文档

启动后访问：http://127.0.0.1:8000/docs (Swagger UI)

## 主要 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/fetch` | POST | 单包名查询 |
| `/api/fetch/batch` | POST | 多包名查询 |
| `/api/batch/upload` | POST | 上传 Excel 批量排查 |
| `/api/download` | POST | 提交下载任务 |
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
  "download_concurrency": 3,
  "proxy": "http://127.0.0.1:7897",
  "enabled_sites": ["google_play", "apkpure", "apkcombo", "apkmirror", "apkvision"],
  "retry_times": 2,
  "language": "zh"
}
```

### 站点选择器

编辑 `backend/scrapers/selectors.yaml` 可在站点改版时无需修改代码。

## 运行测试

```bash
pytest tests/ -v
```

## 支持的站点

| 站点 | 后端 | 代理 | 说明 |
|------|------|------|------|
| Google Play | google-play-scraper | 需要 | 最权威来源 |
| APKPure | Fetcher + JS渲染 | 需要 | 绕过 Cloudflare |
| APKCombo | Fetcher | 需要 | /api/app 302跳转 |
| APKMirror | Fetcher + Stealthy | 需要 | 多步跳转 |
| APKVision | StealthySession | 不需要 | CF JS Challenge |

## 从旧版迁移

旧版项目：`C:\Users\Administrator\game-version-check`

本版本复用旧版的核心代码：
- `gvc/parser.py` → `backend/core/parser.py` (90% 复用)
- `gvc/version.py` → `backend/core/version.py` (70% 复用，增强)
- `gvc/http_client.py` → `backend/core/http_client.py` (80% 复用)
- `gvc/sources.py` → `backend/scrapers/*.py` (50-65% 复用)
- `gvc/downloader.py` → `backend/download/extractors.py` (70% 复用)
