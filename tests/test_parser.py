"""HTML 解析器测试."""

from backend.core.parser import (
    extract_version,
    extract_version_code,
    extract_both,
    extract_abis,
)


class TestExtractVersion:
    def test_version_in_class(self):
        html = '<div class="version-info">1.2.3</div>'
        assert extract_version(html) == "1.2.3"

    def test_data_attribute(self):
        html = '<div data-dt-version="4.4.0">Download</div>'
        assert extract_version(html) == "4.4.0"

    def test_meta_version_text(self):
        html = "<span>Version: 3.2.1</span>"
        assert extract_version(html) == "3.2.1"

    def test_no_version(self):
        html = "<div>Hello World</div>"
        assert extract_version(html) is None


class TestExtractVersionCode:
    def test_variant_code(self):
        html = "variant code: 18000"
        assert extract_version_code(html) == "18000"

    def test_data_attribute(self):
        html = '<div data-dt-versioncode="123456">App</div>'
        assert extract_version_code(html) == "123456"

    def test_json_version_code(self):
        html = '"versionCode": "789012"'
        assert extract_version_code(html) == "789012"

    def test_version_code_label(self):
        html = "<span>Version Code: 456789</span>"
        assert extract_version_code(html) == "456789"

    def test_no_code(self):
        html = "<div>Hello World</div>"
        assert extract_version_code(html) is None

    # v3.8: APKPure 详情页多 App 场景 — BS4 按元素语义过滤推广内容
    def test_apkpure_detail_page_with_promotion(self):
        """模拟真实 APKPure 详情页：version-item（目标App）+ aegon-card（推广）"""
        html = """
        <div class="version-item"
             data-dt-version-code="243"
             data-dt-version="1.0.17">
        </div>
        <div class="aegon-card" data-dt-package-name="com.apkpure.aegon"
             data-dt-version_code="3207037"
             data-dt-version="3.20.70">
        </div>
        """
        # BS4 模式 0a 优先返回 version-item 上的 version_code，跳过 aegon-card 推广
        assert extract_version_code(html) == "243"
        # 推广元素的 version_code 被正确过滤
        assert extract_version_code(html, "com.apkpure.aegon") == "243"

    def test_apkpure_aegon_as_target(self):
        """当 com.apkpure.aegon 本身是目标时（页面无 aegon-card 推广）"""
        html = """
        <div class="version-item"
             data-dt-version-code="3207037"
             data-dt-version="3.20.70">
        </div>
        """
        # version-item 不是推广元素，直接提取
        assert extract_version_code(html) == "3207037"

    def test_apkpure_detail_page_no_package(self):
        """无 package 时返回第一个非推广的 version_code"""
        html = """
        <div class="version-item"
             data-dt-version-code="243">
        </div>
        <div class="aegon-card"
             data-dt-version_code="3207037">
        </div>
        """
        # 返回非推广的 version-item 上的值
        assert extract_version_code(html) == "243"

    def test_apkpure_hyphen_separator(self):
        """data-dt-version-code (hyphen) 格式 — APKPure.net 主要格式"""
        html = '<div data-dt-package="com.example.game" data-dt-version-code="21118">Game</div>'
        assert extract_version_code(html, "com.example.game") == "21118"

    def test_apkpure_underscore_separator_legacy(self):
        """data-dt-version_code (underscore) 格式 — 旧版兼容"""
        html = '<div data-dt-package_name="com.example.game" data-dt-version_code="123456">Game</div>'
        assert extract_version_code(html, "com.example.game") == "123456"

    def test_mode10_3digit_code_with_package(self):
        """Mode 10 有 package 限域时应匹配正确的 3 位 version_code"""
        html = """
        <div data-dt-package="com.example.game"
             data-dt-version-code="243">
        </div>
        <div>Version Code: 99999</div>
        """
        # 限域在 package 块内，应返回 243 而非 99999
        assert extract_version_code(html, "com.example.game") == "243"

    def test_mode10_no_package_3digit(self):
        """Mode 10 无 package 时应匹配 3 位 version_code"""
        html = '<span>Version Code: 243</span>'
        assert extract_version_code(html) == "243"


class TestExtractBoth:
    def test_both_present(self):
        html = """
        <div class="version">2.5.0</div>
        <span>Version Code: 25000</span>
        """
        v, vc = extract_both(html)
        assert v == "2.5.0"
        assert vc == "25000"


class TestExtractAbis:
    def test_arm64(self):
        assert "arm64-v8a" in extract_abis("arm64-v8a apk download")

    def test_multiple(self):
        abis = extract_abis("Supports arm64-v8a, armeabi-v7a, and x86")
        assert "arm64-v8a" in abis
        assert "armeabi-v7a" in abis
        assert "x86" in abis

    def test_none(self):
        assert extract_abis("No architecture info") == []
