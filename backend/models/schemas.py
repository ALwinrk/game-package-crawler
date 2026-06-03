"""数据模型 — ApkInfo, DownloadTask, BatchTask, 枚举."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompareStatus(str, Enum):
    MATCHED = "matched"
    NEWER = "newer"
    OLDER = "older"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class ApkInfo:
    """单个站点的 APK 信息."""
    source: str                              # 来源名称
    package: str                             # 包名
    version: str | None = None               # 版本名
    version_code: str | None = None          # 版本号
    version_name: str | None = None          # 版本名（别名）
    release_date: str | None = None          # 发布日期
    file_size: str | None = None             # 文件大小描述
    abis: list[str] = field(default_factory=list)     # 支持的 ABI 架构
    detail_url: str | None = None            # 详情页 URL
    download_urls: list[str] = field(default_factory=list)  # 直链列表
    error: str | None = None                 # 错误信息

    @property
    def ok(self) -> bool:
        return bool(self.version) and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "package": self.package,
            "version": self.version,
            "version_code": self.version_code,
            "version_name": self.version_name,
            "release_date": self.release_date,
            "file_size": self.file_size,
            "abis": self.abis,
            "detail_url": self.detail_url,
            "download_urls": self.download_urls,
            "error": self.error,
        }


@dataclass
class FetchResult:
    """单包名综合排查结果."""
    package: str
    name: str = ""
    expected_version: str | None = None
    expected_version_code: str | None = None
    results: dict[str, ApkInfo] = field(default_factory=dict)
    best_version: str | None = None
    best_version_code: str | None = None
    compare_status: CompareStatus = CompareStatus.NOT_FOUND
    version_name_compare: str | None = None    # 版本名对比详情
    version_code_compare: str | None = None    # 版本号对比详情
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "name": self.name,
            "expected_version": self.expected_version,
            "expected_version_code": self.expected_version_code,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "best_version": self.best_version,
            "best_version_code": self.best_version_code,
            "compare_status": self.compare_status.value,
            "version_name_compare": self.version_name_compare,
            "version_code_compare": self.version_code_compare,
            "error": self.error,
        }


@dataclass
class DownloadTask:
    """下载任务."""
    id: str
    url: str
    package_name: str
    version: str
    arch: str
    save_path: str
    detail_url: str = ""       # 详情页 URL (Playwright 下载时需要)
    total_size: int = 0
    downloaded_size: int = 0
    status: str = "pending"  # pending / downloading / paused / completed / error
    speed: str = ""
    progress_pct: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "package_name": self.package_name,
            "version": self.version,
            "arch": self.arch,
            "save_path": self.save_path,
            "total_size": self.total_size,
            "downloaded_size": self.downloaded_size,
            "status": self.status,
            "speed": self.speed,
            "progress_pct": self.progress_pct,
            "error": self.error,
        }
