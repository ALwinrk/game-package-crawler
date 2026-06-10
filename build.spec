# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 游戏包名爬虫系统 v2.0 单文件打包 (FastAPI + Vue3 + Chromium)."""

import os
import sys
from pathlib import Path

PROJ_ROOT = Path(SPECPATH)  # type: ignore[name-defined]  # noqa: F821

# ── 前端静态文件 ────────────────────────────────────────────
_frontend_dist = PROJ_ROOT / "frontend" / "dist"
_datas = []
if _frontend_dist.exists():
    _datas.append((str(_frontend_dist / "index.html"), "frontend/dist"))
    _datas.append((str(_frontend_dist / "assets"), "frontend/dist/assets"))
    print(f"[spec] Bundling Vue3 frontend from: {_frontend_dist}")
else:
    print("[spec] WARNING: frontend/dist not found! Build with: cd frontend && npm run build")

# ── Chromium Headless Shell (StealthySession 浏览器后端) ──
_chromium_src = ""
_ms_playwright = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
_chromium_headless = os.path.join(_ms_playwright, "chromium_headless_shell-1217", "chrome-headless-shell-win64")
if os.path.isdir(_chromium_headless):
    _chromium_src = _chromium_headless
    print(f"[spec] Bundling Chromium headless shell from: {_chromium_src}")
else:
    _alt_paths = [
        os.path.join(_ms_playwright, "chromium-1217", "chrome-win64"),
    ]
    for _p in _alt_paths:
        if os.path.isdir(_p):
            _chromium_src = _p
            break

if _chromium_src:
    _datas.append((_chromium_src, "chromium"))
    print(f"[spec] Chromium bundled as 'chromium/' ({sum(f.stat().st_size for f in Path(_chromium_src).rglob('*') if f.is_file()) // (1024*1024)} MB)")
else:
    print("[spec] WARNING: Chromium not found! APKMirror/APKVision will not work.")

# ── browserforge 数据 ──
import site
for _sp in site.getsitepackages():
    _af_data = os.path.join(_sp, "apify_fingerprint_datapoints", "data")
    if os.path.isdir(_af_data):
        _datas.append((_af_data, "apify_fingerprint_datapoints/data"))
        print(f"[spec] Bundling apify_fingerprint_datapoints data")
        break

# ── config.json ──
_config_file = PROJ_ROOT / "config.json"
if _config_file.exists():
    _datas.append((str(_config_file), "."))
    print("[spec] Bundling config.json")

# ── Analysis ────────────────────────────────────────────────

a = Analysis(
    [str(PROJ_ROOT / "launcher.py")],
    pathex=[str(PROJ_ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # FastAPI + uvicorn
        "fastapi",
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "fastapi.staticfiles",
        "uvicorn",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "websockets",
        "websockets.legacy",
        "websockets.extensions",
        "python_multipart",
        # HTTP
        "aiohttp",
        "aiofiles",
        "aiofiles.os",
        "multidict",
        "yarl",
        # google-play-scraper
        "google_play_scraper",
        "google_play_scraper.features.app",
        "google_play_scraper.features.search",
        "google_play_scraper.features.permissions",
        "google_play_scraper.constants.element",
        "google_play_scraper.constants.request",
        "google_play_scraper.utils",
        # Scrapling
        "scrapling",
        "scrapling.fetchers",
        "scrapling.fetchers.requests",
        "scrapling.engines",
        "scrapling.engines.static",
        "scrapling.engines._browsers",
        "scrapling.engines._browsers._stealth",
        "scrapling.engines._browsers._chrome",
        "scrapling.engines._browsers._types",
        "scrapling.engines.toolbelt",
        "scrapling.engines.toolbelt.custom",
        "scrapling.engines.toolbelt.fingerprints",
        "scrapling.engines.toolbelt.proxy_rotation",
        "scrapling.core",
        "scrapling.core._types",
        "scrapling.parser",
        "scrapling.spiders",
        # Scrapling deps
        "browserforge",
        "browserforge.headers",
        "browserforge.fingerprints",
        "browserforge.bayesian_network",
        "apify_fingerprint_datapoints",
        "patchright",
        "patchright._impl",
        "patchright._impl._browser_type",
        "patchright.sync_api",
        "patchright.async_api",
        "msgspec",
        # HTTP
        "curl_cffi",
        "bs4",
        "lxml",
        # Data
        "openpyxl",
        "pyyaml",
        # DB
        "sqlalchemy",
        "aiosqlite",
        # Config
        "pydantic",
        "pydantic_settings",
        "pydantic_core",
        # Version
        "packaging",
        # Rate limiting
        "slowapi",
        "slowapi.util",
        "slowapi.errors",
        "limits",
        # Logging
        "loguru",
        # Backend modules
        "backend",
        "backend.main",
        "backend.config",
        "backend.logging_setup",
        "backend.api",
        "backend.api.routes",
        "backend.api.websocket",
        "backend.models",
        "backend.models.schemas",
        "backend.core",
        "backend.core.http_client",
        "backend.core.parser",
        "backend.core.version",
        "backend.core.orchestrator",
        "backend.core.browser_manager",
        "backend.core.cache",
        "backend.scrapers",
        "backend.scrapers.base",
        "backend.scrapers.google_play",
        "backend.scrapers.apkpure",
        "backend.scrapers.apkcombo",
        "backend.scrapers.apkmirror",
        "backend.scrapers.apkvision",
        "backend.download",
        "backend.download.manager",
        "backend.download.extractors",
        "backend.batch",
        "backend.batch.manager",
        "backend.memo",
        "backend.memo.store",
        "backend.db",
        "backend.db.database",
        "backend.cron",
        "backend.cron.update_tracker",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "unittest",
        "http.server",
        "xmlrpc",
        "pydoc",
        "distutils",
        "setuptools",
        "customtkinter",
        "tkinter",
        "matplotlib",
        "PIL",
        "numpy",
        "pandas",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="游戏包名爬虫系统_v3.7",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
