import logging
import os
from email.parser import BytesParser
from unittest.mock import patch, MagicMock, call

import pytest
import requests

from notifiers import NotifierManager, build_notifier, available_notifiers
from notifiers.base import BaseNotifier, register
from config import load_config

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def app_config():
    return load_config(os.path.join(FIXTURES_DIR, "valid_config.yaml"))


@pytest.fixture
def logger():
    return logging.getLogger("notifier_test")


class TestPluginRegistry:
    def test_available_notifiers_include_all(self):
        names = available_notifiers()
        assert "email" in names
        assert "wecom" in names
        assert "webhook" in names

    def test_build_notifier_returns_none_for_unknown(self, app_config, logger):
        assert build_notifier("slack", app_config.notifiers_config, logger) is None

    def test_build_notifier_returns_instance(self, app_config, logger):
        n = build_notifier("email", app_config.notifiers_config, logger)
        assert n is not None
        assert isinstance(n, BaseNotifier)
        assert n.notifier_name == "email"

    def test_register_custom_plugin(self, app_config, logger):
        class_name = "__test_plugin__"

        @register(class_name)
        class TestPlugin(BaseNotifier):
            send_call = None
            alert_call = None

            def send_change(self, name, url, summary, report_path):
                TestPlugin.send_call = (name, url)

            def send_alert(self, name, url, error_msg, failure_count):
                TestPlugin.alert_call = (name, error_msg, failure_count)

        assert class_name in available_notifiers()
        inst = build_notifier(class_name, app_config.notifiers_config, logger)
        assert inst is not None
        inst.send_change("N", "http://u", "sum", None)
        assert TestPlugin.send_call == ("N", "http://u")
        inst.send_alert("N", "http://u", "boom", 3)
        assert TestPlugin.alert_call == ("N", "boom", 3)


class TestEmailNotifier:
    def test_send_change_with_report(self, tmp_path, app_config, logger):
        report = tmp_path / "r.html"
        report.write_text("<h1>diff</h1>", encoding="utf-8")
        n = build_notifier("email", app_config.notifiers_config, logger)

        with patch("smtplib.SMTP_SSL") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__.return_value = mock_server
            MockSMTP.return_value = mock_server
            n.send_change("SiteA", "https://a", "line diff", str(report))
            mock_server.login.assert_called_once_with("test@test.com", "testpass")
            mock_server.sendmail.assert_called_once()
            args = mock_server.sendmail.call_args[0]
            assert args[0] == "test@test.com"
            assert args[1] == ["admin@test.com"]

            raw = args[2]
            msg = BytesParser().parsebytes(raw.encode("utf-8"))
            assert msg["Subject"] == "[网页变化] SiteA"
            assert "SiteA" in msg.get_payload()[0].get_payload()

    def test_send_alert(self, app_config, logger):
        n = build_notifier("email", app_config.notifiers_config, logger)
        with patch("smtplib.SMTP_SSL") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value = mock_server
            n.send_alert("SiteA", "https://a", "timeout", 5)
            mock_server.sendmail.assert_called_once()
            raw = mock_server.sendmail.call_args[0][2]
            msg = BytesParser().parsebytes(raw.encode("utf-8"))
            assert "[告警]" in msg["Subject"]
            payload = msg.get_payload()[0].get_payload()
            assert "timeout" in payload
            assert "5" in payload

    def test_send_without_ssl(self, tmp_path, app_config, logger):
        cfg = dict(app_config.notifiers_config)
        cfg["email"]["use_ssl"] = False
        n = build_notifier("email", cfg, logger)
        with patch("smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value = mock_server
            n.send_change("S", "https://s", "x", None)
            mock_server.starttls.assert_called_once()


class TestWeComNotifier:
    def test_send_change(self, app_config, logger):
        n = build_notifier("wecom", app_config.notifiers_config, logger)
        with patch("requests.post") as m:
            m.return_value = MagicMock(status_code=200)
            n.send_change("WxSite", "https://w", "摘要内容", None)
            m.assert_called_once()
            url = m.call_args[0][0]
            assert "qyapi.weixin.qq.com" in url
            payload = m.call_args[1]["json"]
            assert payload["msgtype"] == "markdown"
            content = payload["markdown"]["content"]
            assert "WxSite" in content
            assert "摘要内容" in content

    def test_send_alert(self, app_config, logger):
        n = build_notifier("wecom", app_config.notifiers_config, logger)
        with patch("requests.post") as m:
            m.return_value = MagicMock(status_code=200)
            n.send_alert("WxSite", "https://w", "network down", 7)
            payload = m.call_args[1]["json"]
            content = payload["markdown"]["content"]
            assert "network down" in content
            assert "7" in content
            assert "告警" in content


class TestWebhookNotifier:
    def test_send_change(self, app_config, logger):
        n = build_notifier("webhook", app_config.notifiers_config, logger)
        with patch("requests.request") as m:
            m.return_value = MagicMock(status_code=200)
            n.send_change("HookSite", "https://h", "diff sum", "/reports/r.html")
            m.assert_called_once()
            method, url = m.call_args[0]
            assert method == "POST"
            assert url == "https://test.example.com/notify"
            kwargs = m.call_args[1]
            assert kwargs["headers"]["Content-Type"] == "application/json"
            assert "Bearer test-token" in kwargs["headers"]["Authorization"]
            payload = kwargs["json"]
            assert payload["event"] == "website_changed"
            assert payload["name"] == "HookSite"
            assert payload["url"] == "https://h"
            assert payload["summary"] == "diff sum"
            assert payload["report_path"] == "/reports/r.html"
            assert "timestamp" in payload

    def test_send_alert(self, app_config, logger):
        n = build_notifier("webhook", app_config.notifiers_config, logger)
        with patch("requests.request") as m:
            m.return_value = MagicMock(status_code=200)
            n.send_alert("HookSite", "https://h", "DNS error", 4)
            payload = m.call_args[1]["json"]
            assert payload["event"] == "website_failure"
            assert payload["failure_count"] == 4
            assert payload["error"] == "DNS error"


class TestNotifierManager:
    def test_send_skips_unknown(self, app_config, logger, caplog):
        mgr = NotifierManager(app_config, logger)
        with patch("requests.post") as m:
            m.return_value = MagicMock(status_code=200)
            mgr.send(["wecom", "unknown_one"], "N", "http://u", "s", None)
        assert m.called
        assert any("未知的通知方式" in rec.message for rec in caplog.records)

    def test_send_alert_handles_exception(self, app_config, logger, caplog):
        mgr = NotifierManager(app_config, logger)
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("boom")):
            mgr.send_alert(["wecom"], "N", "http://u", "err", 3)
        assert any("告警通知失败" in rec.message for rec in caplog.records)
