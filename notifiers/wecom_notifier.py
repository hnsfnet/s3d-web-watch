from datetime import datetime

import requests

from .base import BaseNotifier, register


@register("wecom")
class WeComNotifier(BaseNotifier):
    def send_change(self, name, url, summary, report_path):
        cfg = self.cfg
        if not cfg:
            return
        content = (
            f"**网页变化检测**\n"
            f"> 网页名称: <font color=\"info\">{name}</font>\n"
            f"> URL: [{url}]({url})\n"
            f"> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**变化摘要:**\n```\n{summary}\n```"
        )
        self._post(cfg["webhook_url"], content)
        self.logger.info("企业微信通知已发送")

    def send_alert(self, name, url, error_msg, failure_count):
        cfg = self.cfg
        if not cfg:
            return
        content = (
            f"**⚠️ 连续抓取失败告警**\n"
            f"> 网页名称: <font color=\"warning\">{name}</font>\n"
            f"> URL: [{url}]({url})\n"
            f"> 连续失败次数: <font color=\"warning\">{failure_count}</font>\n"
            f"> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**错误信息:**\n```\n{error_msg}\n```"
        )
        self._post(cfg["webhook_url"], content)
        self.logger.info("企业微信告警已发送")

    def _post(self, webhook_url, content):
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        resp = requests.post(webhook_url, json=payload, timeout=30)
        resp.raise_for_status()
