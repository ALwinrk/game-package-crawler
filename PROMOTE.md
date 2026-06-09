# 任务：优化启动流程，实现“打开工具立即显示上次抓取的实时面板数据”

## 背景
当前系统 v3.2 的实时更新面板（APKPure/APKCombo/APKVision）数据由定时任务 `update_tracker.py` 每 30 分钟抓取一次并存入 `daily_updates` 表。前端 `/api/daily-updates` 接口直接从数据库读取数据。

**问题**：在全新安装或数据库为空时，前端打开面板需要等待第一次抓取完成（约 10-30 秒）才能看到数据；即使数据库已有数据，启动时仍会先执行一次抓取，导致用户打开工具后需要等待几秒才能看到内容（如果抓取较慢）。

**目标**：
1. 实现“打开工具后立即显示上次抓取的数据（如果有）”，无需等待新抓取。
2. 后台抓取任务正常进行，数据在后台更新，前端可轮询刷新。

## 解决方案

### 1. 修改 `backend/main.py` 的 `lifespan` 函数

- 将“首次抓取”改为 **不阻塞启动**（让数据库已有数据立即提供服务），但为了确保新安装时有数据，可以设置一个**轻量级预检**：如果数据库中没有数据，则同步等待首次抓取完成（带超时）。否则，直接跳过等待，让后台任务慢慢更新。

```python
# 在 lifespan 中
from backend.cron.update_tracker import update_once, run_periodic_updates
from backend.db.database import get_db_connection

# 检查数据库是否有任何实时面板数据
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM daily_updates")
has_data = cursor.fetchone()[0] > 0
conn.close()

# 启动定时循环任务（后台）
update_task = asyncio.create_task(run_periodic_updates())

if not has_data:
    # 首次运行无数据 → 等待首次抓取（最多 15 秒）
    try:
        await asyncio.wait_for(update_once(), timeout=15.0)
        print("首次实时面板数据抓取完成")
    except asyncio.TimeoutError:
        print("首次抓取超时，面板可能暂时为空，后台继续")
else:
    # 已有数据 → 立即启动后台任务，不等待
    asyncio.create_task(update_once())  # 非阻塞刷新
2. 确保 /api/daily-updates 直接返回数据库内容
该端点目前已经直接从 daily_updates 表查询并返回，无需修改。但要确保即使数据库为空也返回空列表（而非错误）。

3. 前端 DailyUpdates.vue 调整（可选）
前端挂载时立即请求 /api/daily-updates，如果返回空数据且轮询尚未开始，可显示“暂无数据，稍后自动刷新”。不需要等待后端的首次抓取。

4. 验证行为
全新环境（数据库为空）：启动后等待最多 15 秒完成首次抓取，前端请求会阻塞直到抓取完成（或超时）。之后面板有数据。

已有数据的环境：启动后前端立即显示上次抓取的数据（几秒内），后台任务在 30 分钟后才更新数据，用户无感知。

交付物
修改 backend/main.py 中的 lifespan 函数，按照上述逻辑实现。

额外优化（可选）
为了减少启动时的等待时间，可以将 update_once() 的重试次数降低，或仅抓取少量页面（例如 1 页）作为快速填充。

如果希望数据库为空时也立即返回空列表（不阻塞启动），可以去掉 if not has_data 中的 await，让后台任务异步填充。但这样用户首次打开会看到空面板，体验稍差。