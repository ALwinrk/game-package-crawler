"""版本号处理 — 标准化、比较、最佳版本判定（增强版，复用 gvc/version.py）."""

from __future__ import annotations

import re
from collections import Counter

from packaging.version import Version, InvalidVersion


def normalize(v: str) -> str:
    """标准化版本号字符串.

    - 去除前导 v/V
    - 空格/下划线/连字符 → 点号
    - 处理 "Varies with device"

    Examples:
        "v4.4.0" → "4.4.0"
        "4 4 0"  → "4.4.0"
        "Varies with device" → ""
    """
    if not v or v.lower() in ("varies with device", "varies"):
        return ""
    return re.sub(r'^[vV]\s*', '', re.sub(r'[\s\-_]+', '.', v.strip()))


def parse_version_tuple(v: str) -> tuple[int, ...]:
    """将版本字符串解析为整数元组以便比较.

    Examples:
        "4.4.0" → (4, 4, 0)
        "4.4"   → (4, 4)
    """
    n = normalize(v)
    if not n:
        return ()
    parts = []
    for part in n.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts)


def compare_versions(a: str, b: str) -> int:
    """比较两个版本号（增强版）.

    策略:
    1. 若均为纯数字 → 转 int 比较
    2. 若为点分格式(如 1.2.3) → 使用 packaging.version.Version
    3. 若包含字母后缀(如 2.3.4-beta) → 分段比较（数字优先，后缀字典序）

    Returns:
        -1: a < b
         0: a == b
         1: a > b
    """
    na = normalize(a)
    nb = normalize(b)
    if na == nb:
        return 0
    if not na:
        return -1
    if not nb:
        return 1

    # 尝试 packaging.version.Version（支持 semver + 预发布后缀）
    try:
        va = Version(na)
        vb = Version(nb)
        if va < vb:
            return -1
        elif va > vb:
            return 1
        return 0
    except InvalidVersion:
        pass

    # 回退到元组比较
    ta = parse_version_tuple(na)
    tb = parse_version_tuple(nb)
    if ta == tb:
        return 0
    max_len = max(len(ta), len(tb))
    ta_padded = ta + (0,) * (max_len - len(ta))
    tb_padded = tb + (0,) * (max_len - len(tb))
    if ta_padded < tb_padded:
        return -1
    elif ta_padded > tb_padded:
        return 1
    return 0


def compare_version_codes(a: str | int, b: str | int) -> int | None:
    """比较两个 version code（整数比较）.

    Returns:
        -1: a < b（有更新）
         0: a == b
         1: a > b
        None: 无法解析
    """
    try:
        ia, ib = int(a), int(b)
    except (ValueError, TypeError):
        return None
    if ia < ib:
        return -1
    elif ia > ib:
        return 1
    return 0


def best_version(versions: list[str], google_version: str | None = None) -> str:
    """从多个数据源结果中判定最佳版本.

    判定策略：
    1. 版本号被 ≥2 个数据源一致报告 → 直接采纳
    2. 仅一个数据源有结果 → 采纳该源
    3. 多源均有结果但无共识 → 优先 Google Play
    4. 否则取最新版本
    """
    if not versions:
        return ""

    counts = Counter(versions)
    top = counts.most_common(1)[0]
    if top[1] >= 2 or len(versions) == 1:
        return top[0]

    if google_version and google_version in versions:
        return google_version

    # 取版本号最大者
    try:
        return str(max(Version(v) for v in versions))
    except (InvalidVersion, ValueError):
        return max(versions, key=lambda v: parse_version_tuple(v))


def best_version_code(codes: list[str]) -> str:
    """从多个 version code 中判定最佳值.

    策略:
    1. 同一 code 被 ≥2 个源一致报告 → 直接采纳
    2. 仅一个源有 code → 采纳该源
    3. 无共识 → 取数值最大的
    """
    if not codes:
        return ""

    counts = Counter(codes)
    top = counts.most_common(1)[0]
    if top[1] >= 2 or len(codes) == 1:
        return top[0]

    try:
        return str(max(int(c) for c in codes))
    except (ValueError, TypeError):
        return codes[0]


def is_plausible_version(version: str) -> bool:
    """版本号合理性校验.

    拒绝明显异常的版本号:
      - >4 段的版本号 (如 2.723.787 可能是版本号编码)
      - 单段超过 5 位数字 (如 2723787)
      - 空或纯数字无点 (只有主版本号是合理的, 但至少要有格式)

    合理示例: 1.2.3, 7.5.102, 1.2.183, 2025.04.01
    不合理示例: 2.723.787 (APKPure 常见错误), 2723787
    """
    if not version or not version.strip():
        return False
    v = version.strip()
    parts = v.split(".")
    if len(parts) > 4:
        return False
    for p in parts:
        if not p.isdigit():
            continue
        if len(p) > 5:
            return False
    return True


def check_for_update(
    best_v: str,
    best_vc: str | None,
    current_v: str,
    current_vc: str,
) -> tuple[bool, str]:
    """判定是否有更新.

    Returns:
        (has_update, detail) — detail 为描述字符串.
    """
    # 策略 1：version code 对比
    if best_vc and current_vc:
        cmp = compare_version_codes(current_vc, best_vc)
        if cmp is not None:
            if cmp == -1:
                return True, f"vc:{current_vc}→{best_vc}"
            if cmp == 0 and current_v and normalize(best_v) != normalize(current_v):
                return True, f"{current_v}→{best_v} (vc:{best_vc})"
            return False, "-"

    # 策略 2：版本名对比
    if current_v and best_v and normalize(best_v) != normalize(current_v):
        detail = f"{current_v}→{best_v}"
        if best_vc:
            detail += f" (vc:{best_vc})"
        return True, detail

    if not current_v and best_v:
        return False, "首次记录"
    return False, "-"
