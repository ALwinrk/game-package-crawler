游戏包名爬虫系统 v3.7 — 低配置电脑内存优化方案（不削弱功能）
一、核心原则
零功能降级：所有爬虫源（APKPure、APKCombo、APKMirror、APKVision、Google Play）依然全量启用，浏览器必须运行，所有超时、重试参数不变。

仅优化资源利用：通过复用、惰性加载、及时释放、减少冗余缓存来降低内存峰值，而不是禁用功能。

可配置但默认不削弱：提供可选的低内存模式开关（默认关闭），由用户自主决定是否启用（启用后不会跳过任何站点，仅调整并发与缓存策略）。

二、内存占用主要来源（无法避免但可优化）
组件	占用	优化思路
Playwright 浏览器进程	150-250 MB	保持常驻，但降低页面并发数（playwright_concurrency=1 仍能支持所有站点，只是串行处理慢速源，不丢失功能）
爬虫并发请求	每个请求 10-30 MB	降低 scraper_concurrency 到 3（不影响数据完整性，只是速度变慢）
内存缓存（TTL）	30-50 MB	关闭内存缓存，直接读 SQLite（增加毫秒级延迟，可接受）
前端 Vue 组件	80-150 MB	懒加载非首屏组件，释放内存
日志输出	CPU/I/O	异步+减少控制台输出
三、具体优化措施（不削弱功能）
3.1 降低 Playwright 页面并发数（保留浏览器）
修改：将 playwright_concurrency 默认值从 2 改为 1（低配模式）。

慢速源（APKMirror、APKVision）将串行处理，速度变慢，但完全可用。

浏览器进程仍常驻，内存仍占用，但并发页面减少可降低额外内存。

配置："playwright_concurrency": 1（用户可自行改回 2）

3.2 降低整体爬虫并发（不丢数据）
修改：低配模式下建议 scraper_concurrency=3（原 6）。快速源（GP、APKPure、APKCombo）将串行，总耗时增加，但每个请求仍会成功。

3.3 关闭内存缓存（改用 SQLite）
新增配置：enable_memory_cache（默认 true），低配模式设为 false。

每次查询直接读取 SQLite，不再缓存到内存。增加几毫秒延迟，但释放 30-50 MB 内存。

3.4 降低实时面板前端轮询频率
修改：低配模式下 frontend_poll_interval=600（10 分钟），仍能更新数据，但减少网络和渲染开销。

3.5 前端组件懒加载
实现：在 App.vue 中将非首屏组件（BatchPanel, DownloadQueue, SettingsPanel, DailyUpdates）改为异步加载。首屏只加载 PackageInput 和 ResultTable。

用户切换到对应选项卡时才加载组件，降低初始内存。

3.6 日志优化
低配模式自动将 log_level 设为 WARNING，并禁用控制台输出（仅写文件）。减少 CPU 和 I/O 压力。

3.7 浏览器启动参数优化（不减少能力）
在 browser_manager.py 中增加 Chromium 启动参数，降低内存开销：

python
launch_args = [
    "--disable-dev-shm-usage",   # 减少共享内存使用
    "--no-sandbox",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding"
]
这些参数不影响功能，仅降低资源占用。

四、低配模式一键切换（不损失功能）
提供 config_low_mem.json 模板，用户复制替换即可：

json
{
  "scraper_concurrency": 3,
  "playwright_concurrency": 1,
  "batch_concurrency": 2,
  "download_concurrency": 2,
  "enable_memory_cache": false,
  "frontend_poll_interval": 600,
  "log_level": "WARNING",
  "enable_console_log": false
}
并且保留所有站点的启用，不删除任何源。

五、自动检测（可选）
在 launcher.py 中加入内存检测，若总内存 < 4GB，弹窗询问是否自动应用低配模式，用户确认后才修改，绝不强制。

六、效果预估
内存峰值：从 1.2GB 降至 800-900 MB，低配电脑可运行。

功能完整性：100% 保持，所有站点依然爬取，只是速度变慢。

用户体验：启动后首屏更快，面板轮询间隔更长，但数据依然更新。

七、总结
本方案从不禁用浏览器，也从不删除任何站点，仅通过降低并发、关闭内存缓存、前端懒加载、优化启动参数等手段，在不丢失任何功能的前提下，让低配电脑也能运行。用户可以根据自己的硬件条件选择是否启用低配模式，默认保持原有高并发高缓存配置。