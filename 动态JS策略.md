### 5.1.6 针对 JS 动态加载站点的处理策略（APKPure & APKCombo）

#### 背景
APKPure 存在 Cloudflare 5秒盾，需要执行 JS 挑战；APKCombo 的下载链接通过前端 JS 动态生成。传统 requests + BeautifulSoup 无法直接获取真实下载地址。

#### 解决方案：Playwright 无头浏览器（小规模专用）

**选型理由**（针对日20款场景）：
- 实现简单，无需逆向 API，维护成本低。
- 成功率接近100%，不受站点前端重构影响（仅需等待选择器）。
- 单次启动浏览器开销约 1-2 秒，20次/天完全可接受。

**技术实现要点**：

1. **浏览器实例管理**：
   - 全局只启动**一个持久化浏览器上下文**（Playwright `launch_persistent_context`），所有爬取任务复用该实例。
   - 每个站点的每次请求使用**新页面**（`browser.new_page()`），用后关闭页面，但不关闭浏览器。
   - 程序启动时初始化浏览器，退出时关闭。

2. **超时与等待策略**：
   - 页面加载超时：15 秒。
   - 等待关键元素：下载按钮或包含版本信息的容器出现（例如 `selector="a[download]"` 或 `div.version-info`）。
   - 若超时未找到元素，则视为该站点不可用，记录日志并返回空结果。

3. **反爬规避**：
   - 使用 Playwright 内置的 `stealth` 插件（`playwright-stealth`）隐藏自动化特征。
   - 随机化视口大小、鼠标移动（可省略，小规模影响不大）。
   - 代理配置：支持通过 `proxy` 参数传入 Clash 代理地址（如 `http://127.0.0.1:7890`）。

4. **具体站点处理**：

| 站点 | 关键选择器（示例） | 提取逻辑 |
|------|-------------------|----------|
| APKPure | `#download_link` 或 `a[data-download-url]` | 等待下载按钮可见后，获取 `href` 属性。若需要点击后才生成链接，则执行 `page.click()` 并监听网络响应。 |
| APKCombo | `a[data-download-id]` 或 `button.download-button` | 模拟点击后，从网络响应中捕获包含 `.apk` 的 URL（通过 `page.wait_for_response()`）。 |

5. **降级策略**：
   - 若 Playwright 启动失败（如缺少浏览器驱动），则自动禁用这两个站点，并在 GUI 中提示用户手动安装浏览器（`playwright install`）。
   - 用户也可在设置中直接禁用 JS 依赖站点，仅使用其他静态站点。

**代码结构示例（供 Claude 参考）**：
```python
# 在 BaseScraper 中增加可选的 Playwright 支持
class APKPureScraper(BaseScraper):
    def __init__(self, use_playwright: bool = True):
        self.use_playwright = use_playwright
        self.browser = None  # 由全局管理器注入

    async def fetch(self, package_name: str) -> List[ApkInfo]:
        if self.use_playwright:
            return await self._fetch_with_playwright(package_name)
        else:
            return await self._fetch_with_requests(package_name)  # 降级

    async def _fetch_with_playwright(self, package_name: str):
        page = await self.browser.new_page()
        try:
            url = f"https://apkpure.com/p/{package_name}"
            await page.goto(url, timeout=15000)
            await page.wait_for_selector("#download_link", timeout=10000)
            download_url = await page.get_attribute("#download_link", "href")
            # ... 提取其他信息
            return [ApkInfo(...)]
        except Exception as e:
            logger.error(f"APKPure Playwright 失败: {e}")
            return []
        finally:
            await page.close()

全局浏览器管理器：

在 FastAPI 启动事件中创建 async with async_playwright() as p: browser = await p.chromium.launch(...)。

将 browser 对象注入到每个需要 Playwright 的爬虫策略类中。

应用关闭时调用 await browser.close()。

性能影响评估：

单个包名同时查询 5 个站点，其中 2 个使用 Playwright（APKPure, APKCombo），其他 3 个使用 requests。

Playwright 页面打开 + 等待选择器 ≈ 3-5 秒，与 requests 并行执行，总耗时仍为 5 秒左右。

日处理 20 个包名，累计浏览器运行时间约 100-200 秒，对电脑资源影响可忽略。

备选方案（不采纳，但记录供参考）：

使用第三方 API 服务（如 apkpure-python 库）：可能过时或不稳定。

手动导出下载链接：不适合自动化工具。