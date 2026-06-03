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
