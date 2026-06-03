"""版本比较函数测试."""

import pytest
from backend.core.version import (
    normalize,
    parse_version_tuple,
    compare_versions,
    compare_version_codes,
    best_version,
    best_version_code,
    check_for_update,
)


class TestNormalize:
    def test_removes_v_prefix(self):
        assert normalize("v4.4.0") == "4.4.0"
        assert normalize("V5.0.1") == "5.0.1"

    def test_replaces_separators(self):
        assert normalize("4 4 0") == "4.4.0"
        assert normalize("4-4-0") == "4.4.0"
        assert normalize("4_4_0") == "4.4.0"

    def test_varies_with_device(self):
        assert normalize("Varies with device") == ""
        assert normalize("Varies") == ""

    def test_empty_input(self):
        assert normalize("") == ""
        assert normalize(None) == ""


class TestParseVersionTuple:
    def test_simple(self):
        assert parse_version_tuple("4.4.0") == (4, 4, 0)
        assert parse_version_tuple("10.0") == (10, 0)

    def test_single_number(self):
        assert parse_version_tuple("5") == (5,)

    def test_invalid(self):
        assert parse_version_tuple("abc") == ()


class TestCompareVersions:
    def test_equal(self):
        assert compare_versions("1.0.0", "1.0.0") == 0
        assert compare_versions("v1.0", "1.0") == 0

    def test_less_than(self):
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("1.9.0", "1.10.0") == -1

    def test_greater_than(self):
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("10.0", "9.9.9") == 1

    def test_semver_prerelease(self):
        # packaging.version 支持预发布后缀
        assert compare_versions("2.0.0-beta", "2.0.0") == -1
        assert compare_versions("2.0.1", "2.0.0-beta") == 1

    def test_empty_handling(self):
        assert compare_versions("", "1.0") == -1
        assert compare_versions("1.0", "") == 1


class TestCompareVersionCodes:
    def test_less_than(self):
        assert compare_version_codes("100", "200") == -1

    def test_greater_than(self):
        assert compare_version_codes(300, 200) == 1

    def test_equal(self):
        assert compare_version_codes("100", 100) == 0

    def test_invalid(self):
        assert compare_version_codes("abc", "200") is None
        assert compare_version_codes(None, 100) is None


class TestBestVersion:
    def test_consensus(self):
        assert best_version(["1.0.0", "1.0.0", "1.0.1"]) == "1.0.0"

    def test_single_source(self):
        assert best_version(["1.0.0"]) == "1.0.0"

    def test_no_consensus_prefer_google(self):
        result = best_version(["1.0.0", "1.0.1", "1.0.2"], google_version="1.0.1")
        assert result == "1.0.1"

    def test_empty(self):
        assert best_version([]) == ""


class TestBestVersionCode:
    def test_consensus(self):
        assert best_version_code(["100", "100", "200"]) == "100"

    def test_no_consensus_max(self):
        assert best_version_code(["100", "300", "200"]) == "300"

    def test_empty(self):
        assert best_version_code([]) == ""


class TestCheckForUpdate:
    def test_version_code_newer(self):
        has, detail = check_for_update("2.0", "200", "1.0", "100")
        assert has is True
        assert "100" in detail and "200" in detail

    def test_version_code_same(self):
        has, detail = check_for_update("2.0", "100", "2.0", "100")
        assert has is False

    def test_version_name_only(self):
        has, detail = check_for_update("2.0.0", None, "1.0.0", "")
        assert has is True
        assert "1.0.0" in detail
