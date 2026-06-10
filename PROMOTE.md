实时游戏面板手动切换数据源功能设计文档
一、需求概述
在现有的实时游戏面板（DailyUpdates）中，增加手动选择数据源的功能，允许用户仅刷新自己关心的源，避免每次都全量爬取所有源（APKPure、APKCombo、APKCombo Trending、APKVision Updated、APKVision New），从而减少不必要的网络请求和服务器负载，提升刷新效率。

典型使用场景：

只想查看 APKVision 新游戏 → 仅选择 apkvision_new，其他源不刷新（保留上次数据）。

只想同时查看 APKPure 和 APKCombo 热门 → 选择 apkpure 和 apkcombo，不刷新其他。

二、可行性分析
✅ 完全可行，且对现有功能无负面影响。

当前后端刷新接口已支持 fire-and-forget 模式，可扩展接受参数 sources。

数据库存储按源隔离（source 字段），可以独立更新单个源的数据而不影响其他源。

前端已有丰富的 UI 组件（多选框、复选框组），易于集成。

三、设计方案
3.1 后端修改
3.1.1 修改刷新 API 接受源参数
当前端点：

POST /api/daily-updates/refresh （全量刷新）

POST /api/daily-updates/refresh-incremental （增量刷新）

修改后：

两个端点均增加可选 JSON 参数 sources，类型为字符串数组，例如 ["apkpure", "apkcombo"]。

若未提供 sources 或数组为空，则保持原有行为（刷新所有已配置的源）。

若提供了 sources，则仅刷新指定的源，其他源的数据在数据库中保持不变。

实现要点：

在 update_tracker.py 中新增函数 refresh_sources(source_list, incremental=False)。

该函数根据 incremental 标志调用原有的抓取逻辑，但只执行列表中源对应的抓取函数。

对未选中的源，不调用任何抓取函数，也不删除其已有数据。

示例请求：

json
POST /api/daily-updates/refresh
Content-Type: application/json

{
  "sources": ["apkpure", "apkcombo"]
}
3.1.2 独立抓取函数支持
当前 update_tracker.py 中已有按源的独立抓取函数：

fetch_apkpure()

fetch_apkcombo()

fetch_apkcombo_trending()

fetch_apkvision_updated()

fetch_apkvision_new()

这些函数均独立调用并写入数据库。refresh_sources 只需按需调用并处理异常。

3.1.3 状态反馈（可选）
由于采用 fire-and-forget 模式，刷新立即返回。可增加 GET /api/daily-updates/refresh-status 接口，返回每个源的最近刷新状态（成功/失败/正在刷新），供前端显示进度。但不是必须，可后续优化。

3.2 前端修改
3.2.1 新增数据源选择器
在 DailyUpdates.vue 组件的工具栏（现有“手动刷新”按钮旁边）增加一个下拉多选框或按钮组，用于选择要刷新的源。

组件建议：使用 el-dropdown + el-checkbox-group，或使用 el-popover 内含复选框。

示例 UI：

text
[ 选择数据源 ▼ ]  [ 全量刷新 ]  [ 增量刷新 ]
点击“选择数据源”弹出面板，列出所有源（带复选框）：

☑ APKPure 热门

☑ APKCombo 热门

☑ APKCombo 最新更新

☑ APKVision 最近更新

☑ APKVision 新游戏

用户勾选后，关闭面板。后续点击“全量刷新”或“增量刷新”时，仅刷新勾选的源。

3.2.2 刷新逻辑修改
当用户点击“全量刷新”或“增量刷新”时，前端收集当前勾选的源列表。

若列表非空，调用对应的 API（/api/daily-updates/refresh 或 /refresh-incremental），并在请求体中附带 sources 数组。

若列表为空（未勾选任何源），提示用户至少选择一个源，或默认全选。

提供“全选”快捷按钮，一键选择所有源，恢复原有行为。

3.2.3 用户提示
刷新过程中，由于是 fire-and-forget，前端可显示全局 loading 或 toast 提示“正在刷新所选源，请稍后查看”。

若部分源刷新失败，可通过轮询状态接口（如实现）或依赖后续自动定时刷新恢复。

3.3 数据库与数据一致性
不同源的数据存储在同一张 daily_updates 表中，通过 source 字段区分。

刷新选中源时，执行 DELETE FROM daily_updates WHERE source = ? 然后插入新数据（或使用 INSERT OR REPLACE）。不影响未选中源的数据。

前端展示时，各标签页直接从数据库读取对应源的数据，因此未刷新的源仍显示上次抓取的内容，符合预期。

3.4 性能与资源影响
用户主动选择少量源刷新时，爬虫负载显著降低，对低配电脑尤其友好。

支持用户按需刷新，避免了不必要的全量抓取，总体资源消耗减少。

不影响原有的定时自动增量刷新（仍按配置 update_check_interval 全量或增量执行）。定时任务可沿用原有逻辑，或也支持按配置的源列表执行（可后续扩展）。

四、注意事项
定时任务与手动刷新的关系：
定时任务（每30分钟）仍保持原有行为（刷新全部源或增量全源），以保证数据及时性。用户手动刷新只是补充，不影响自动任务。

源名称一致：
前端传递给后端的源名称必须与后端抓取函数标识完全一致。建议定义常量：

apkpure

apkcombo

apkcombo_trending

apkvision_updated

apkvision_new

错误处理：
若用户选择的某个源刷新失败（如站点被封），其他源仍应继续刷新，失败信息记录日志，前端不阻塞。

首次加载面板：
v3.6 启动后面板为空，用户需手动刷新。此时若未选择任何源，应提示用户先选择源，或默认全选。

UI 兼容性：
所有修改仅影响实时更新面板的刷新行为，不影响排查、下载等核心功能。

五、实施步骤（供开发参考）
后端：

修改 routes.py 中 /api/daily-updates/refresh 和 /refresh-incremental 接口，解析 sources 参数。

在 update_tracker.py 中实现 refresh_sources(sources, incremental)，调用对应的抓取函数。

确保异常隔离，单个源失败不影响其他源。

前端：

在 DailyUpdates.vue 中添加数据源选择组件（复选框组）。

修改 refresh() 和 refreshIncremental() 方法，读取选中源列表，发送请求。

增加“全选”按钮及交互提示。

测试：

选择单个源刷新 → 仅该源表格数据更新，其他源不变。

选择多个源刷新 → 对应源更新。

不选择任何源 → 提示用户或默认全选。

全量刷新（原行为）→ 所有源更新。