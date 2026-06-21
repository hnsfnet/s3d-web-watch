import hashlib
import logging
import os

import pytest

from comparator import ContentComparator, CompareResult

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def read_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def cmp(tmp_path):
    logger = logging.getLogger("cmp_test")
    return ContentComparator(str(tmp_path / "contents"), logger)


def test_compute_hash():
    content = "hello world"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert ContentComparator._compute_hash(None, content) == expected


def test_prepare_no_selector_no_patterns():
    html = read_fixture("sample_v1.html")
    logger = logging.getLogger("x")
    cmp_obj = ContentComparator("/tmp", logger)
    out = cmp_obj.prepare(html)
    assert out == html


def test_prepare_css_selector_extract():
    html = read_fixture("sample_v1.html")
    logger = logging.getLogger("x")
    cmp_obj = ContentComparator("/tmp", logger)
    out = cmp_obj.prepare(html, selector="#main")
    assert "欢迎来到示例页面" in out
    assert "价格: 99元" in out
    assert 'id="sidebar"' not in out
    assert "广告1" not in out


def test_prepare_apply_ignore_patterns():
    html = read_fixture("sample_v1.html")
    logger = logging.getLogger("x")
    cmp_obj = ContentComparator("/tmp", logger)
    patterns = [r'token="[A-Za-z0-9]+"', r"data-timestamp=\"\\d+\""]
    out = cmp_obj.prepare(html, ignore_patterns=patterns)
    assert 'token="abc123xyz"' not in out
    assert "data-timestamp=\"1718918400\"" not in out
    assert "欢迎来到示例页面" in out


def test_compare_new_content(cmp):
    result = cmp.compare("site1", "<p>first</p>")
    assert result.status == CompareResult.NEW
    assert result.new_content == "<p>first</p>"
    assert result.old_content is None


def test_compare_unchanged(cmp):
    cmp.compare("site1", "<p>same</p>")
    result = cmp.compare("site1", "<p>same</p>")
    assert result.status == CompareResult.UNCHANGED
    assert result.old_content is None
    assert result.new_content is None


def test_compare_changed(cmp):
    cmp.compare("site1", "<p>old</p>")
    result = cmp.compare("site1", "<p>new</p>")
    assert result.status == CompareResult.CHANGED
    assert result.old_content == "<p>old</p>"
    assert result.new_content == "<p>new</p>"


def test_compare_after_ignore_patterns_same(cmp):
    v1 = read_fixture("sample_v1.html")
    v2 = read_fixture("sample_v2.html")
    patterns = [
        r'token="[A-Za-z0-9]+"',
        r"data-timestamp=\"\\d+\"",
        r"data-ad-id=\"[^\"]+\"",
    ]
    v1_main = cmp.prepare(v1, selector="#main", ignore_patterns=patterns)
    v1_side = cmp.prepare(v1, selector="#sidebar", ignore_patterns=patterns)
    v2_side = cmp.prepare(v2, selector="#sidebar", ignore_patterns=patterns)
    cmp.compare("side", v1_side)
    result = cmp.compare("side", v2_side)
    assert result.status == CompareResult.UNCHANGED


def test_compare_after_ignore_patterns_different(cmp):
    v1 = read_fixture("sample_v1.html")
    v2 = read_fixture("sample_v2.html")
    patterns = [r'token="[A-Za-z0-9]+"', r"data-timestamp=\"\\d+\""]
    v1_main = cmp.prepare(v1, selector="#main", ignore_patterns=patterns)
    v2_main = cmp.prepare(v2, selector="#main", ignore_patterns=patterns)
    cmp.compare("main", v1_main)
    result = cmp.compare("main", v2_main)
    assert result.status == CompareResult.CHANGED
    assert "价格: 99元" in result.old_content
    assert "价格: 89元" in result.new_content


def test_format_change_log(cmp):
    old = "line1\nline2\nline3"
    new = "line1\nchanged\nline3"
    out = cmp.format_change_log("MySite", "https://x", old, new)
    assert "[变化检测]" in out
    assert "MySite" in out
    assert "https://x" in out
    assert "line2" in out
    assert "changed" in out


def test_build_summary(cmp):
    old = "a\nb\nc"
    new = "a\nB\nc"
    s = cmp.build_summary(old, new)
    assert "-b" in s
    assert "+B" in s


def test_hash_persisted_between_instances(tmp_path):
    logger = logging.getLogger("x")
    c1 = ContentComparator(str(tmp_path), logger)
    c1.compare("x", "content A")

    c2 = ContentComparator(str(tmp_path), logger)
    result = c2.compare("x", "content A")
    assert result.status == CompareResult.UNCHANGED
