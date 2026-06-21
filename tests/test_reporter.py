import logging
import os
import re
from datetime import datetime

import pytest

from reporter import DiffReporter

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def read_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def reporter(tmp_path):
    logger = logging.getLogger("rep_test")
    return DiffReporter(str(tmp_path / "reports"), logger)


def test_generate_report_creates_file(reporter):
    old = "line1\nline2\nline3"
    new = "line1\nchanged\nline3"
    ts_before = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reporter.generate("MyPage", "https://example.com/page", old, new)
    ts_after = datetime.now().strftime("%Y%m%d_%H%M%S")

    assert os.path.exists(path)
    basename = os.path.basename(path)
    assert basename.startswith("MyPage_")
    assert basename.endswith(".html")

    ts_pattern = r"MyPage_(\d{8}_\d{6})\.html"
    m = re.match(ts_pattern, basename)
    assert m is not None
    file_ts = m.group(1)
    assert ts_before <= file_ts <= ts_after


def test_report_contains_timestamp_and_name(reporter):
    old = "v1"
    new = "v2"
    path = reporter.generate("PricePage", "https://shop/item1", old, new)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "PricePage" in html
    assert "https://shop/item1" in html
    assert "变化报告" in html
    assert "检测时间" in html
    today = datetime.now().strftime("%Y-%m-%d")
    assert today in html


def test_report_highlights_diff(reporter):
    old = read_fixture("sample_v1.html")
    new = read_fixture("sample_v2.html")
    path = reporter.generate("SampleSite", "https://sample", old, new)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "价格: 99元" in html
    assert "价格: 89元" in html


def test_report_with_empty_content(reporter):
    path = reporter.generate("EmptySite", "https://empty", "", "")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "变化报告" in html
    assert "EmptySite" in html


def test_report_cleanup_after_test(tmp_path):
    logger = logging.getLogger("rep_test")
    rep = DiffReporter(str(tmp_path / "cleanup_reports"), logger)
    path1 = rep.generate("A", "http://a", "x", "y")
    path2 = rep.generate("B", "http://b", "p", "q")
    assert os.path.exists(path1)
    assert os.path.exists(path2)

    for p in [path1, path2]:
        os.remove(p)
    assert not os.path.exists(path1)
    assert not os.path.exists(path2)


def test_report_dir_created_if_not_exists(tmp_path):
    logger = logging.getLogger("rep_test")
    new_dir = tmp_path / "brand_new_reports"
    assert not new_dir.exists()
    DiffReporter(str(new_dir), logger)
    assert new_dir.exists()
