```
# APK 下载稳定性与架构识别改进方案 (v2.8.1 适配)

## 一、现有问题分析

根据项目文档 v2.8.1 及用户反馈，当前下载模块存在以下核心缺陷：

| 问题现象 | 根本原因 | 影响 |
|---------|----------|------|
| 下载有时成功、有时失败 | 1. Playwright 捕获直链时可能因站点动态签名超时而失效<br>2. aiohttp 下载时未处理重定向或临时链接过期<br>3. 无重试队列，单次失败即标记为错误 | 用户体验差，需反复点击下载 |
| 架构显示 `unknown` | 1. 爬虫未从页面提取 ABI 信息<br>2. 下载链接文件名中可能包含 `arm64-v8a` 等标识，但未解析<br>3. APK 文件本身未校验 | 用户无法区分 32/64 位，可能下载错误版本 |
| 动态链接提取不稳定 | 1. `extractors.py` 依赖静态规则，对站点改版脆弱<br>2. Playwright 点击下载按钮的选择器覆盖不全<br>3. 未对捕获的链接进行有效性预检 | 链接失效导致下载 403/404 |

## 二、解决方案总览

采用 **“增强版 Playwright 捕获 + 多级回退 + 离线架构识别”** 的三层策略：

1. **链路稳定性**：增加重试、多选择器、链接有效性预检、备用下载器（aria2）。
2. **架构识别**：从文件名、页面 ABI 标签、APK 文件头（`apkanalyzer`）三个维度识别，最终显示具体架构。
3. **健壮性**：引入下载队列持久化重试、断点续传增强、超时自适应。

## 三、具体实现方案

### 3.1 下载链接获取优化

#### 3.1.1 改进 `capture_download_url` 方法（`browser_manager.py`）

- 增加**多选择器遍历**，支持不同站点版本。
- 增加**等待网络空闲** + 监听所有 `download` 事件，取第一个有效的 `.apk` 链接。
- 增加**超时后可重试**（例如 3 次，每次递增等待）。
- 捕获到链接后，立即发送一个 `HEAD` 请求验证是否可访问（响应码 200/206），若失败则降级。

```python
async def capture_download_url(self, page_url: str, source: str, retries=3) -> str:
    for attempt in range(retries):
        try:
            # 原有逻辑，但增加页面刷新和等待
            ...
            # 验证链接
            if await self._check_url_accessible(download_url):
                return download_url
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("无法捕获有效下载链接")
```



#### 3.1.2 链接有效性预检函数

python

```
async def _check_url_accessible(self, url: str) -> bool:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.head(url, timeout=5, allow_redirects=True) as resp:
                return resp.status in (200, 206)
        except:
            return False
```



### 3.2 架构识别增强（`extractors.py` + 新工具）

#### 3.2.1 从页面提取 ABI 信息

在爬虫解析详情页时，增加提取 ABI 字段：

- APKPure: 查找 `div.abi` 或 `data-abi` 属性。
- APKCombo: 查找 `.architecture` 或 `dt-arch`。
- APKMirror: 变体列表中包含 `arm64-v8a`、`armeabi-v7a` 等文本。

#### 3.2.2 从下载链接文件名识别

正则匹配常见架构标识：

python

```
ARCH_PATTERNS = {
    "arm64-v8a": re.compile(r"arm64|aarch64|arm64-v8a", re.I),
    "armeabi-v7a": re.compile(r"armeabi-v7a|armv7a", re.I),
    "x86_64": re.compile(r"x86_64|x64", re.I),
    "x86": re.compile(r"x86", re.I),
    "universal": re.compile(r"universal|all", re.I),
}
```



#### 3.2.3 离线分析 APK 文件头（可选，但准确）

下载完成后，使用 `aapt` 或 Python 库 `androguard` 解析 APK 的 `lib/` 目录，获取原生库支持的架构。这可以作为最终验证，并在 UI 中显示“实际架构”。

**集成步骤**：

- 安装 `androguard`：`pip install androguard`
- 下载完成后异步调用 `get_apk_abis(apk_path)` 返回列表，更新数据库和前端。

python

```
from androguard.core.apk import APK
def get_apk_abis(path):
    apk = APK(path)
    return apk.get_android_abi_attributes()  # 返回 ['arm64-v8a', ...]
```



#### 3.2.4 前端显示

- 如果爬虫提取到架构 → 直接显示（如 `arm64-v8a`）
- 否则从文件名推断 → 显示 `推测: arm64-v8a`
- 下载完成后，后台分析后更新为 `确认: arm64-v8a`

### 3.3 下载器增强：引入 aria2 作为可选后端

由于 FDM 集成受阻（无 Web 界面），改用 **aria2** 作为备用下载器。aria2 支持 RPC 接口，可稳定处理重定向、断点续传、多线程，且完全开源。

#### 3.3.1 aria2 集成方式

- 用户可选：在配置中启用 `downloader: "aria2"`。
- 系统自动下载 aria2c.exe（或要求用户提供路径）。
- 启动 aria2 进程：`aria2c --enable-rpc --rpc-listen-port=6800 --dir=./downloads`
- 通过 `aria2p` Python 库提交任务，获取实时进度。

#### 3.3.2 回退策略

- 若 aria2 未安装或启动失败，自动回退到 aiohttp。
- 若 aiohttp 失败（403/404），自动尝试 Playwright 捕获直链后再用 aria2。

### 3.4 下载队列健壮性增强

#### 3.4.1 自动重试机制

在 `DownloadManager` 中增加失败重试队列：

- 下载失败（网络错误、链接失效）→ 放入重试队列，延迟 10s 后重试，最多 3 次。
- 若仍失败，标记为“失败”并给出原因（链接失效、架构不支持等）。

#### 3.4.2 下载速率监控与自适应

- 使用 aiohttp 下载时，每 2 秒计算平均速度，若速度 < 10KB/s 持续 10 秒，则自动切换到 aria2 尝试多线程加速。

#### 3.4.3 数据库记录架构信息

扩展 `download_tasks` 表，增加 `architecture` 字段（存储识别的架构）和 `abi_source` 字段（记录识别来源：'page'/'filename'/'analyzed'）。

## 四、安全性保持

- 所有下载链接仍需经过 SSRF 防护（`validate_url`）。
- aria2 RPC 端口仅监听 `127.0.0.1`，通过 `--rpc-secret` 设置简单密钥。
- 架构分析仅对已下载文件执行，避免外部注入。

## 五、健壮性措施总结

| 问题         | 解决方式                           |
| :----------- | :--------------------------------- |
| 动态链接失效 | 捕获后立即验证 + 重试 + 备用下载器 |
| 架构未知     | 三级识别（页面→文件名→APK分析）    |
| 下载速率慢   | 自动切换 aria2 多线程              |
| 下载中断     | 断点续传 + 重试队列                |
| 站点改版     | 选择器外置 + 多备选 + 降级到 API   |

## 六、实现步骤与交付物

1. **修改 `browser_manager.py`**：增加链接验证、重试机制。
2. **修改 `extractors.py`**：增加 ABI 提取和文件名识别。
3. **新增 `backend/utils/apk_analyzer.py`**：提供 `get_apk_abis()` 函数。
4. **集成 aria2**：新增 `backend/download/aria2_manager.py`，提供启停和任务提交接口。
5. **修改 `download/manager.py`**：增加重试队列、速率监控、架构分析回调。
6. **更新数据库**：`download_tasks` 增加 `architecture` 和 `abi_source` 列。
7. **前端修改**：在下载队列卡片中显示架构标签（带颜色区分：64位绿色，32位蓝色，未知灰色）。
8. **更新 `config.json`**：新增 `downloader_backend` (`aiohttp`/`aria2`)、`aria2_path`、`enable_apk_analysis` 等选项。

## 七、验收标准

- APKPure/APKCombo 链接捕获成功率 > 95%（重试 3 次后）。
- 下载失败的自动重试有效，最终失败原因明确。
- 架构识别准确率 > 90%（实际测试 50 个不同 APK）。
- 使用 aria2 后下载速度提升 2-5 倍。
- 系统保持原有安全防护（SSRF、路径遍历、速率限制），无新增漏洞。

> 本方案不依赖外部付费软件，完全基于开源组件实现，且与 v2.8.1 架构无缝兼容。