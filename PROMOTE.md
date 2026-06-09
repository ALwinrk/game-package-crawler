# 增加 APKVision 游戏更新/新游戏面板（仅取最近 20 条）- 设计文档 (v3.0 适配)

## 一、需求概述

在“实时更新”选项卡中，为 **APKVision** 增加两个新的数据源：

- **最近更新游戏**（源：`https://apkvision.org/updated/`）
- **新上线游戏**（源：`https://apkvision.org/games/`）

每个源仅抓取页面中自然排序的 **前 20 款游戏**（不分页），减少抓取复杂度和服务器负载。数据存储与 APKPure/APKCombo 共享 `daily_updates` 表，通过 `source` 字段区分（`apkvision_updated` 和 `apkvision_new`）。

## 二、数据库与后端设计

### 2.1 无需修改表结构

现有 `daily_updates` 表已足够，只需约定两个新的 `source` 值。

### 2.2 抓取函数（仅取前 20 条）

复用 `http_client.stealth_get()` 绕过 Cloudflare，解析 HTML，并**截取前 20 条结果**。

#### 2.2.1 最新更新游戏（`/updated/`）

页面结构：游戏列表位于 `.main-news-grid` 中的 `.main-news` 元素。取前 20 个。

```python
async def fetch_apkvision_updated() -> list[dict]:
    url = "https://apkvision.org/updated/"
    html = await stealth_get(url)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    articles = soup.select(".main-news-grid .main-news")[:20]   # 只取 20 条
    for article in articles:
        name_el = article.select_one(".main-news-title")
        name = name_el.get_text(strip=True) if name_el else ""
        version_els = article.select(".main-news-cat")
        version = version_els[0].get_text(strip=True) if version_els else ""
        href = article.get("href", "")
        # 包名从 href 最后一段提取（如果存在）
        package_name = href.rstrip("/").split("/")[-1] if href else name.lower().replace(" ", "_")
        items.append({
            "app_name": name,
            "package_name": package_name,
            "version_name": version,
            "version_code": "",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    return items
2.2.2 新上线游戏（/games/）
该页面包含 Best New Games 区域（.mainb-grid .mainb-item）和下方列表（.main-news-grid .main-news）。合并两个区域，按页面顺序取前 20 条。

python
async def fetch_apkvision_new() -> list[dict]:
    url = "https://apkvision.org/games/"
    html = await stealth_get(url)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # 先取 Best New Games
    for article in soup.select(".mainb-grid .mainb-item"):
        name_el = article.select_one(".mainb-title")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        version_els = article.select(".mainb-cat")
        version = version_els[0].get_text(strip=True) if version_els else ""
        href = article.get("href", "")
        package_name = href.rstrip("/").split("/")[-1] if href else name.lower().replace(" ", "_")
        items.append({
            "app_name": name,
            "package_name": package_name,
            "version_name": version,
            "version_code": "",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        if len(items) >= 20:
            return items[:20]
    # 若不足 20，再取下方普通列表
    for article in soup.select(".main-news-grid .main-news"):
        if len(items) >= 20:
            break
        name_el = article.select_one(".main-news-title")
        name = name_el.get_text(strip=True) if name_el else ""
        version_els = article.select(".main-news-cat")
        version = version_els[0].get_text(strip=True) if version_els else ""
        href = article.get("href", "")
        package_name = href.rstrip("/").split("/")[-1] if href else name.lower().replace(" ", "_")
        items.append({
            "app_name": name,
            "package_name": package_name,
            "version_name": version,
            "version_code": "",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    return items[:20]
2.3 集成到定时任务
在 update_tracker.py 的 update_once() 中并行抓取四个源：

python
async def update_once():
    await asyncio.gather(
        fetch_source_with_circuit_breaker("apkpure"),
        fetch_source_with_circuit_breaker("apkcombo"),
        fetch_source_with_circuit_breaker("apkvision_updated"),
        fetch_source_with_circuit_breaker("apkvision_new"),
        return_exceptions=True
    )
    set_last_modified(datetime.now())
2.4 API 返回格式调整
修改 /api/daily-updates 端点，将四个来源的数据分别放入 apkpure、apkcombo、apkvision_updated、apkvision_new 字段。前端按需展示。

2.5 前端展示
在 DailyUpdates.vue 中增加两个标签页：

APKVision 最近更新

APKVision 新游戏

表格列与现有保持一致：游戏名称、包名、版本名、版本号、更新时间。版本号字段可留空或显示“-”。

三、健壮性措施
如果解析结果为空（少于 1 条），抛出异常，触发熔断，保留旧数据。

若 package_name 提取失败，使用游戏名称拼音化作为 fallback（不影响功能）。

使用 stealth_get() 自动处理 Cloudflare，无需额外配置。

四、验收标准
后端抓取 /updated/ 和 /games/ 页面，返回列表不超过 20 条。

数据成功入库，source 分别为 apkvision_updated 和 apkvision_new。

API 返回包含四个来源的数据。

前端正确展示两个新标签页，数据不与其他源混淆。

熔断、事务保护正常工作。

五、交付物
修改 backend/cron/update_tracker.py（新增两个抓取函数 + 调度）

修改 backend/api/routes.py（扩展 API 返回字段）

修改 frontend/src/components/DailyUpdates.vue（新增标签页）

由于仅取 20 条，无需分页，代码更简洁，对服务器压力小。