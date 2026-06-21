from datetime import datetime

import requests

from .base import BaseNotifier, register


@register("webhook")
class WebhookNotifier(BaseNotifier):
    def send_change(self, name, url, summary, report_path):
        cfg = self.cfg
        if not cfg:
            return
        payload = {
            "event": "website_changed",
            "name": name,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "report_path": report_path,
        }
        self._send(cfg, payload)
        self.logger.info("Webhook 通知已发送 (website_changed)")

    def send_alert(self, name, url, error_msg, failure_count):
        cfg = self.cfg
        if not cfg:
            return
        payload = {
            "event": "website_failure",
            "name": name,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "failure_count": failure_count,
            "error": error_msg,
        }
        self._send(cfg, payload)
        self.logger.info("Webhook 告警已发送 (website_failure)")

    def _send(self, cfg, payload):
        method = cfg.get("method", "POST").upper()
        headers = cfg.get("headers", {})
        resp = requests.request(method, cfg["url"], json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
