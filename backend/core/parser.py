"""HTML 解析 — 从页面提取版本号和 version code（复用 gvc/parser.py）."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# ── 版本号正则模式 ───────────────────────────────────────
_VERSION_PATTERNS: list[str] = [
    r'^[\d]+\.[\d]+(?:\.[\d]+)*$',
]

_ATTR_CANDIDATES: list[str] = [
    "data-dt-version",
    "data-version",
    "data-app-version",
    "data-release-version",
    "data-versioncode",
]


def extract_version(html: str) -> str | None:
    """从 HTML 中提取版本号.

    策略（按优先级）：
    1. class 名含 "version" → 精确匹配 x.y.z
    2. data-* 属性中的版本号
    3. itemprop="version"
    4. 全文 "Version: x.y.z" 模式
    5. 全文 `>x.y.z<` 模式（兜底）

    v3.8: 过滤推广元素（aegon/store/promo/ad/buff），避免误取推广 App 的版本号。
    """
    soup = BeautifulSoup(html, "html.parser")

    def _is_promo(elem) -> bool:
        classes = ' '.join(elem.get('class', []))
        return any(kw in classes.lower() for kw in ('aegon', 'store', 'promo', 'ad', 'buff'))

    # 策略 1：class 名含 version（跳过推广元素）
    for elem in soup.select('[class*="version"]'):
        if _is_promo(elem):
            continue
        text = elem.get_text(strip=True)
        if _is_version(text):
            return text

    # 策略 2：data-* 属性（跳过推广元素）
    for attr in _ATTR_CANDIDATES:
        for elem in soup.find_all(attrs={attr: True}):
            if _is_promo(elem):
                continue
            v = elem[attr].strip()
            if re.match(r'^\d+\.\d+', v) and len(v) < 25:
                return v

    # 策略 3：Schema.org itemprop（跳过推广元素）
    for elem in soup.select('[itemprop="version"]'):
        if _is_promo(elem):
            continue
        m = re.search(r'([\d]+\.[\d]+(?:\.[\d]+)?)', elem.get_text(strip=True))
        if m:
            return m.group(1)

    # 策略 4：全文 "Version: …" 模式
    text = soup.get_text()
    for pattern in [
        r'(?:Version|v\.?)\s*:?\s*([\d]+\.[\d]+(?:\.[\d]+)?)',
        r'版本[：:]\s*([\d]+\.[\d]+(?:\.[\d]+)?)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1)

    # 策略 5：兜底 — 标签内嵌版本号
    m = re.search(r'>\s*([\d]+\.[\d]+\.[\d]+)\s*<', html)
    if m:
        return m.group(1)

    return None


def extract_version_code(html: str, package: str = "") -> str | None:
    """从 HTML 中提取 version code（1-12 位数字）.

    v3.8: 优先使用 BeautifulSoup 从非推广元素提取，避免误匹配 APKPure 推广 App。
    按特异性从高到低依次尝试，首个命中即返回。
    """
    soup = BeautifulSoup(html, "html.parser")

    def _is_promo(elem) -> bool:
        """检查元素是否属于推广/推荐/广告内容."""
        classes = ' '.join(elem.get('class', []))
        return any(kw in classes.lower() for kw in ('aegon', 'store', 'promo', 'ad', 'buff'))

    # ═══ v3.8: BS4 结构化提取（过滤推广元素） ═══

    # 模式 0a：data-dt-version-code（连字符）— APKPure 详情页主格式，version-item 元素
    for item in soup.select('[data-dt-version-code]'):
        if _is_promo(item):
            continue
        vc = item.get('data-dt-version-code', '').strip()
        if vc and vc.isdigit() and 1 <= len(vc) <= 12:
            return vc

    # 模式 0b：data-dt-version_code（下划线）— 旧版格式，过滤 aegon-card 等推广
    for item in soup.select('[data-dt-version_code]'):
        if _is_promo(item):
            continue
        vc = item.get('data-dt-version_code', '').strip()
        if vc and vc.isdigit() and 1 <= len(vc) <= 12:
            return vc

    # 模式 0c：data-dt-versioncode（无分隔符）— 搜索页/旧版格式，过滤推广
    for item in soup.select('[data-dt-versioncode]'):
        if _is_promo(item):
            continue
        vc = item.get('data-dt-versioncode', '').strip()
        if vc and vc.isdigit() and 3 <= len(vc) <= 12:
            return vc

    # ═══ 以下为全局兜底模式（原有逻辑，用于非 APKPure 页面） ═══

    # 模式 0d：data-version_code（无 dt- 前缀）
    m = re.search(r'data-version_code\s*=\s*["\']?(\d{3,12})', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 1：variant code: NNNNNN（APKCombo 常见）
    m = re.search(r'variant\s*code[:\s]*(\d{3,12})', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 2：x.y.z (NNNNNN)（版本号后括号跟 code）
    for m in re.finditer(r'(\d+\.\d+\.\d+)\s*[\(（]\s*(\d{3,12})\s*[\)）]', html):
        return m.group(2)

    # 模式 2b：x.y.z <tag>(NNNN)</tag> — APKCombo blur span 格式
    m = re.search(r'(\d+\.\d+\.\d+)\s*(?:<[^>]+>\s*)?[\(（]\s*(\d{3,12})\s*[\)）]', html)
    if m:
        return m.group(2)

    # 模式 2c：x.y.z (NNNN) 但括号和 code 间可能有任意 HTML — 先 strip tags 再试
    clean = re.sub(r'<[^>]+>', ' ', html)
    for m in re.finditer(r'(\d+\.\d+\.\d+)\s*[\(（]\s*(\d{3,12})\s*[\)）]', clean):
        return m.group(2)

    # 模式 3b：data-versioncode="NNNNNN"
    m = re.search(r'data-versioncode\s*=\s*["\']?(\d{3,12})', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 4：<meta> 标签内嵌 versionCode
    m = re.search(
        r'<meta\s+(?:property|name)\s*=\s*["\']?versioncode["\']?\s+content\s*=\s*["\'](\d{3,12})["\']',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1)

    # 模式 5：JSON 内嵌 "versionCode": "NNNNNN"
    m = re.search(r'["\']versionCode["\']\s*:\s*["\']?(\d{3,12})["\']?', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 6：纯文本标签 "Version Code: NNNNNN"
    m = re.search(r'(?:Version\s*Code|version\s*code)\s*[：:]\s*(\d{3,12})', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 7：备选 data 属性 data-app-versioncode
    m = re.search(r'data-app-versioncode\s*=\s*["\']?(\d{3,12})', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 8：APK 文件名内嵌 code（_123456_.apk 或 -123456.apk）
    m = re.search(r'[_-](\d{5,12})[_.]apk', html, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 9：定义列表 <dt>Version Code</dt><dd>NNNNNN</dd>
    m = re.search(
        r'<d[td]>\s*(?:Version\s*Code|版本代码)\s*</d[td]>\s*<d[td]>\s*(\d{3,12})\s*</d[td]>',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1)

    # 模式 10：兜底 — version/ver/vc/code 关键词后的 :或= 后接数字
    # v3.8: 在非推广元素的属性中搜索，避免匹配 aegon-card 等推广 App
    _pat10 = re.compile(r'(?:version|ver|vc|code)\s*[：:=]\s*(\d{3,12})\b', re.IGNORECASE)
    for elem in soup.find_all():
        if _is_promo(elem):
            continue
        for val in elem.attrs.values():
            if isinstance(val, str):
                m = _pat10.search(val)
                if m:
                    return m.group(1)
    # 全局兜底：全文搜索（非 APKPure 页面可能没有 class 标记）
    m = _pat10.search(html)
    if m:
        return m.group(1)

    return None


def extract_both(html: str, package: str = "") -> tuple[str | None, str | None]:
    """一次性提取版本号和 version code，共享同一个 BeautifulSoup 实例.

    Returns:
        (version, version_code) 元组.
    """
    version = extract_version(html)
    vcode = extract_version_code(html, package)
    return version, vcode


def extract_abis(text: str) -> list[str]:
    """从文本中提取 ABI 架构列表."""
    abis = []
    abi_patterns = [
        ("arm64-v8a", r'arm64[-\s]?v8a'),
        ("armeabi-v7a", r'armeabi[-\s]?v7a'),
        ("x86_64", r'x86[_\s]?64'),
        ("x86", r'\bx86\b'),
        ("universal", r'universal'),
    ]
    for name, pattern in abi_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            if name not in abis:
                abis.append(name)
    return abis


def extract_file_size(html: str) -> str | None:
    """从 HTML 中提取文件大小."""
    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(MB|GB|KB|mb|gb|kb)',
        html,
    )
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def _is_version(text: str) -> bool:
    """检查是否像有效版本号."""
    if not text or len(text) < 3 or len(text) > 24:
        return False
    return bool(re.match(r'^[\d]+\.[\d]+(?:\.[\d]+)*$', text))
