"""BaseScraper — 所有站点爬虫的抽象基类."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.schemas import ApkInfo


class BaseScraper(ABC):
    """爬虫基类，新站点只需实现 fetch() 方法."""

    name: str = "base"

    @abstractmethod
    async def fetch(self, package: str) -> ApkInfo:
        """根据包名抓取 APK 信息.

        Args:
            package: Android 包名.

        Returns:
            ApkInfo 包含版本、架构、下载链接等.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.name}Scraper>"
