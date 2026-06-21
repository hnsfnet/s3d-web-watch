import os
import logging

import pytest
import yaml

from config import load_config, setup_logger, AppConfig, WebsiteConfig

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_load_valid_config():
    path = os.path.join(FIXTURES_DIR, "valid_config.yaml")
    cfg = load_config(path)
    assert isinstance(cfg, AppConfig)
    assert cfg.log_file == "test_changes.log"
    assert cfg.content_dir == ".test_contents"
    assert cfg.report_dir == "test_reports"
    assert cfg.default_timeout == 10
    assert cfg.max_failures == 2
    assert len(cfg.websites) == 2


def test_website_config_attributes():
    path = os.path.join(FIXTURES_DIR, "valid_config.yaml")
    cfg = load_config(path)
    w1 = cfg.websites[0]
    assert isinstance(w1, WebsiteConfig)
    assert w1.name == "Test Site 1"
    assert w1.url == "https://test1.example.com"
    assert w1.interval_minutes == 30
    assert w1.interval_seconds == 1800
    assert w1.selector == "#main"
    assert w1.timeout_seconds is None
    assert w1.ignore_patterns == ['token="[A-Za-z0-9]+"', 'data-timestamp="\\d+"']
    assert w1.notifiers == ["email", "wecom"]
    assert w1.effective_timeout(10) == 10


def test_selector_optional():
    path = os.path.join(FIXTURES_DIR, "valid_config.yaml")
    cfg = load_config(path)
    w2 = cfg.websites[1]
    assert w2.selector is None
    assert w2.ignore_patterns == []
    assert w2.timeout_seconds is None


def test_effective_timeout_with_override():
    data = {
        "name": "X",
        "url": "http://x",
        "interval_minutes": 5,
        "timeout_seconds": 45,
    }
    w = WebsiteConfig(data)
    assert w.effective_timeout(10) == 45


def test_config_file_not_found():
    path = os.path.join(FIXTURES_DIR, "does_not_exist.yaml")
    with pytest.raises(FileNotFoundError):
        load_config(path)


def test_invalid_yaml_format():
    path = os.path.join(FIXTURES_DIR, "invalid_yaml.yaml")
    with pytest.raises(yaml.YAMLError):
        load_config(path)


def test_missing_required_fields():
    path = os.path.join(FIXTURES_DIR, "missing_required.yaml")
    cfg = load_config(path)
    assert cfg.websites[0].name == "Missing URL"
    with pytest.raises(KeyError):
        _ = cfg.websites[0].url


def test_setup_logger(tmp_path):
    log_file = tmp_path / "test.log"
    logger = setup_logger(str(log_file))
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.INFO
    assert len(logger.parent.handlers) >= 1


def test_setup_logger_writes_file(tmp_path):
    log_file = tmp_path / "test.log"
    logger = setup_logger(str(log_file))
    msg = "hello from test"
    logger.info(msg)
    for h in logger.parent.handlers:
        h.flush()
    assert os.path.exists(str(log_file))
    with open(str(log_file), "r", encoding="utf-8") as f:
        content = f.read()
    assert msg in content
