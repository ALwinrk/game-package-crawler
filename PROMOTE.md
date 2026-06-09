# APKPure Cloudflare 封禁根本解决方案（免费，无住宅代理）

## 问题定位

APKPure 使用 Cloudflare Turnstile 检测自动化行为，主要依据：
1. **TLS 指纹**：curl_cffi 虽能模拟，但长期单一指纹易被关联
2. **无头浏览器特征**：StealthySession 默认配置可能暴露 WebDriver
3. **请求规律**：固定间隔、固定顺序、无随机性
4. **单 IP 高频**：即使代理池，若出口 IP 不变，仍被封

## 免费解决方案总览

| 层级 | 措施 | 实现位置 | 效果 |
|------|------|----------|------|
| 1 | StealthySession 自动求解 | `http_client.py` | 必须，已启用 |
| 2 | TLS 指纹轮换 | `http_client.py` | 核心突破 |
| 3 | 请求随机化（间隔+顺序） | `update_tracker.py` | 辅助 |
| 4 | 降低频率 + 批次暂停 | `config.json` | 必要 |
| 5 | Playwright 反检测增强 | `browser_manager.py` | 加固 |
| 6 | 熔断器 + 人工干预接口 | `update_tracker.py` | 兜底 |

## 一、TLS 指纹轮换（curl_cffi 层）

### 修改 `backend/core/http_client.py`

增加指纹池，每次请求随机选择：

```python
from curl_cffi import requests
import random

FINGERPRINTS = [
    "chrome110", "chrome116", "chrome120",
    "edge101", "safari15_5", "firefox110"
]

def get_random_fingerprint():
    return random.choice(FINGERPRINTS)

async def fetch_with_fingerprint(url, proxy=None):
    fp = get_random_fingerprint()
    session = requests.AsyncSession(impersonate=fp, proxy=proxy)
    return await session.get(url, timeout=10)
修改 StealthySession 的 __init__，允许传入 impersonate 参数并随机化。

二、请求随机化（行为层）
2.1 修改 backend/cron/update_tracker.py
在抓取循环中加入随机延迟和顺序打乱：

python
import asyncio
import random

# 打乱分类列表
categories = list(APKPURE_CATEGORIES.items())
random.shuffle(categories)

for name, url in categories:
    # 抓取逻辑...
    await asyncio.sleep(random.uniform(3.0, 7.0))   # 页间随机暂停
2.2 随机化 User-Agent
在 http_client.py 中维护 UA 池，随机选择：

python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0",
    # ...
]
三、配置调优（config.json）
针对团队使用（日均 200 款），推荐保守配置：

json
{
  "scraper_concurrency": 2,
  "playwright_concurrency": 1,
  "update_check_interval": 7200,
  "daily_updates_pages": 1,
  "stealth_timeout": 60,
  "retry_times": 3,
  "retry_delay": 5.0,
  "request_timeout": 15.0
}
同时，若 APKPure 持续失败，可通过 enabled_sites 临时移除：

json
"enabled_sites": ["google_play", "apkcombo", "apkvision"]
四、Playwright 无头浏览器反检测增强
修改 backend/core/browser_manager.py
在创建浏览器上下文时，增加反检测参数和脚本：

python
context = await browser.new_context(
    viewport={'width': random.randint(1024, 1920), 'height': random.randint(768, 1080)},
    user_agent=random.choice(USER_AGENTS),
    locale='zh-CN',
    timezone_id='Asia/Shanghai',
    ignore_default_args=["--enable-automation"],
    extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"}
)

# 注入 stealth 脚本
await context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
""")
五、熔断器 + 人工干预接口（兜底）
5.1 熔断器实现（update_tracker.py）
python
class CircuitBreaker:
    def __init__(self, name, failure_threshold=3, recovery_timeout=3600):
        self.name = name
        self.failure_count = 0
        self.is_open = False
        self.open_until = 0

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.open()

    def record_success(self):
        self.failure_count = 0
        self.is_open = False

    def open(self):
        self.is_open = True
        self.open_until = time.time() + recovery_timeout

    def is_closed(self):
        if self.is_open and time.time() > self.open_until:
            self.is_open = False
            self.failure_count = 0
        return not self.is_open
在 fetch_apkpure_updates 中集成熔断器，连续失败 3 次后跳过该源 1 小时。

5.2 人工干预接口
当检测到 Turnstile 页面时，将 URL 存入数据库表 captcha_tasks，并通过 WebSocket 向前端推送通知。管理员可点击链接手动完成验证，然后恢复。

简化版：在日志中打印 URL，管理员手动访问解封后，通过 API /api/apkpure/unblock 重置熔断器。

六、监控与恢复建议
在 update_tracker.py 中增加日志：每次抓取成功/失败计数，便于分析封禁规律。

如果连续 2 次失败，自动将 update_check_interval 临时调整为 7200 秒（写回 config.json），避免频繁重试。

定期（如每周）手动更换出口 IP（重启路由器或切换 VPN 节点）。

七、总结
本方案通过指纹轮换、行为随机化、浏览器反检测、熔断器四层防护，在不使用住宅代理的前提下，大幅降低 APKPure 封禁概率。若仍被封，说明 IP 已进入黑名单，唯一的免费办法是更换网络出口 IP（如重启路由器），或临时禁用 APKPure 源。

将这些改进集成到 v3.2 代码库后，APKPure 的可用性将显著提升。