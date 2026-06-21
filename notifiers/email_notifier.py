import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .base import BaseNotifier, register


@register("email")
class EmailNotifier(BaseNotifier):
    def send_change(self, name, url, summary, report_path):
        cfg = self.cfg
        if not cfg:
            return
        msg = MIMEMultipart()
        msg["From"] = cfg["sender"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg["Subject"] = f"[网页变化] {name}"

        body = (
            f"网页名称: {name}\n"
            f"URL: {url}\n"
            f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"变化摘要:\n{summary}\n"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if report_path and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                msg.attach(MIMEText(f.read(), "html", "utf-8"))

        self._smtp_send(cfg, msg)
        self.logger.info("邮件通知已发送")

    def send_alert(self, name, url, error_msg, failure_count):
        cfg = self.cfg
        if not cfg:
            return
        msg = MIMEMultipart()
        msg["From"] = cfg["sender"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg["Subject"] = f"[告警] {name} 连续抓取失败"

        body = (
            f"⚠️ 连续抓取失败告警 ({failure_count}次)\n"
            f"网页: {name}\n"
            f"URL: {url}\n"
            f"错误: {error_msg}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        self._smtp_send(cfg, msg)
        self.logger.info("告警邮件已发送")

    def _smtp_send(self, cfg, msg):
        if cfg.get("use_ssl", True):
            server = smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"], timeout=30)
        else:
            server = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=30)
            server.starttls()
        try:
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["sender"], cfg["recipients"], msg.as_string())
        finally:
            server.quit()
