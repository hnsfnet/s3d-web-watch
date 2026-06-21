#!/usr/bin/env python3
import os
import re
import time
import smtplib
import hashlib
import logging
import difflib
import argparse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import yaml
from bs4 import BeautifulSoup


class Notifier:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def send(self, notifier_names, name, url, report_path, old_content, new_content):
        summary = self._build_summary(old_content, new_content)
        for nname in notifier_names:
            try:
                if nname == "email":
                    self._send_email(name, url, summary, report_path)
                elif nname == "wecom":
                    self._send_wecom(name, url, summary)
                elif nname == "webhook":
                    self._send_webhook(name, url, summary, report_path)
                else:
                    self.logger.warning(f"未知的通知方式: {nname}")
            except Exception as e:
                self.logger.error(f"通知失败 [{nname}]: {e}")

    def _build_summary(self, old_content, new_content):
        old_lines = (old_content or "").splitlines()
        new_lines = (new_content or "").splitlines()
        changes = []
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=2))
        for line in diff[3:13]:
            if line.startswith("+") or line.startswith("-"):
                changes.append(line)
        if len(diff) > 13:
            changes.append("...")
        return "\n".join(changes) if changes else "内容已更新"

    def _send_email(self, name, url, summary, report_path):
        cfg = self.config.get("notifiers", {}).get("email", {})
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
                report_html = f.read()
            msg.attach(MIMEText(report_html, "html", "utf-8"))

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
        self.logger.info("邮件通知已发送")

    def _send_wecom(self, name, url, summary):
        cfg = self.config.get("notifiers", {}).get("wecom", {})
        if not cfg:
            return
        content = (
            f"**网页变化检测**\n"
            f"> 网页名称: <font color=\"info\">{name}</font>\n"
            f"> URL: [{url}]({url})\n"
            f"> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**变化摘要:**\n```\n{summary}\n```"
        )
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        resp = requests.post(cfg["webhook_url"], json=payload, timeout=30)
        resp.raise_for_status()
        self.logger.info("企业微信通知已发送")

    def _send_webhook(self, name, url, summary, report_path):
        cfg = self.config.get("notifiers", {}).get("webhook", {})
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
        method = cfg.get("method", "POST").upper()
        headers = cfg.get("headers", {})
        resp = requests.request(method, cfg["url"], json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        self.logger.info("Webhook 通知已发送")


class DiffReporter:
    def __init__(self, report_dir, logger):
        self.report_dir = report_dir
        self.logger = logger
        os.makedirs(self.report_dir, exist_ok=True)

    def _safe_name(self, name):
        return re.sub(r"[^\w\-]+", "_", name)

    def generate(self, name, url, old_content, new_content):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._safe_name(name)
        filename = f"{safe_name}_{timestamp}.html"
        filepath = os.path.join(self.report_dir, filename)

        old_lines = (old_content or "").splitlines(keepends=True)
        new_lines = (new_content or "").splitlines(keepends=True)

        diff_html = difflib.HtmlDiff(wrapcolumn=120).make_file(
            old_lines, new_lines, fromdesc="上次内容", todesc="当前内容"
        )

        page_title = f"变化报告 - {name} - {timestamp}"
        header = f"""
        <div style="padding:20px;background:#f5f5f5;border-bottom:2px solid #ddd;">
            <h2 style="margin:0 0 10px 0;">{page_title}</h2>
            <p style="margin:4px 0;"><strong>网页名称:</strong> {name}</p>
            <p style="margin:4px 0;"><strong>URL:</strong> <a href="{url}">{url}</a></p>
            <p style="margin:4px 0;"><strong>检测时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        """
        final_html = diff_html.replace("<body>", f"<body>{header}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_html)

        self.logger.info(f"对比报告已生成: {filepath}")
        return filepath


class ContentExtractor:
    @staticmethod
    def extract(html, selector=None):
        if not selector:
            return html
        try:
            soup = BeautifulSoup(html, "lxml")
            elements = soup.select(selector)
            if not elements:
                return ""
            return "\n".join(str(el) for el in elements)
        except Exception as e:
            return html


class WebsiteMonitor:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self.load_config()
        self.content_dir = self.config["settings"]["content_dir"]
        self.log_file = self.config["settings"]["log_file"]
        self.report_dir = self.config["settings"].get("report_dir", "reports")
        self.setup_logging()
        self.last_checked = {}

        os.makedirs(self.content_dir, exist_ok=True)
        self.notifier = Notifier(self.config, self.logger)
        self.reporter = DiffReporter(self.report_dir, self.logger)

    def load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(self.log_file, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(__name__)

    def _safe_name(self, name):
        return name.replace(" ", "_").replace("/", "_")

    def get_content_path(self, name):
        return os.path.join(self.content_dir, f"{self._safe_name(name)}.html")

    def get_hash_path(self, name):
        return os.path.join(self.content_dir, f"{self._safe_name(name)}.hash")

    def fetch_content(self, url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException as e:
            self.logger.error(f"抓取失败 {url}: {e}")
            return None

    def compute_hash(self, content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def read_last_hash(self, name):
        hash_path = self.get_hash_path(name)
        if os.path.exists(hash_path):
            with open(hash_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def save_hash(self, name, content_hash):
        hash_path = self.get_hash_path(name)
        with open(hash_path, "w", encoding="utf-8") as f:
            f.write(content_hash)

    def save_content(self, name, content):
        content_path = self.get_content_path(name)
        with open(content_path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_last_content(self, name):
        content_path = self.get_content_path(name)
        if os.path.exists(content_path):
            with open(content_path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def check_website(self, website):
        name = website["name"]
        url = website["url"]
        selector = website.get("selector")

        self.logger.info(f"检查: {name}" + (f" (selector: {selector})" if selector else ""))

        raw_html = self.fetch_content(url)
        if raw_html is None:
            return

        current_content = ContentExtractor.extract(raw_html, selector)
        if not current_content:
            self.logger.warning(f"内容为空，跳过: {name}")
            return

        current_hash = self.compute_hash(current_content)
        last_hash = self.read_last_hash(name)

        if last_hash is None:
            self.logger.info(f"首次记录: {name}")
            self.save_hash(name, current_hash)
            self.save_content(name, current_content)
            return

        if current_hash == last_hash:
            self.logger.info(f"无变化: {name}")
            return

        last_content = self.read_last_content(name)
        self.log_change(name, url, last_content, current_content)

        report_path = self.reporter.generate(name, url, last_content, current_content)

        notifier_names = website.get("notifiers", [])
        if notifier_names:
            self.notifier.send(notifier_names, name, url, report_path, last_content, current_content)

        self.save_hash(name, current_hash)
        self.save_content(name, current_content)

    def log_change(self, name, url, old_content, new_content):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = (
            f"\n{'='*60}\n"
            f"[变化检测] {timestamp}\n"
            f"网页名称: {name}\n"
            f"URL: {url}\n"
            f"{'='*60}\n"
        )

        if old_content and new_content:
            old_lines = old_content.splitlines()
            new_lines = new_content.splitlines()
            max_lines = min(50, max(len(old_lines), len(new_lines)))

            for i in range(max_lines):
                old_line = old_lines[i] if i < len(old_lines) else ""
                new_line = new_lines[i] if i < len(new_lines) else ""
                if old_line != new_line:
                    log_entry += f"行 {i+1}:\n"
                    log_entry += f"  - {old_line}\n"
                    log_entry += f"  + {new_line}\n"

            if max(len(old_lines), len(new_lines)) > 50:
                log_entry += "... (省略更多差异行)\n"

        log_entry += f"{'='*60}\n"

        self.logger.info(log_entry)

    def should_check(self, website, now):
        name = website["name"]
        interval = website["interval_minutes"] * 60
        last_check = self.last_checked.get(name, 0)
        return now - last_check >= interval

    def run(self):
        self.logger.info("网页内容监控脚本启动")
        self.logger.info(f"监控 {len(self.config['websites'])} 个网页")

        for website in self.config["websites"]:
            selector_info = f" [selector: {website.get('selector', '全部')}]"
            notifier_info = f" [通知: {', '.join(website.get('notifiers', [])) or '无'}]"
            self.logger.info(f"  - {website['name']}: {website['url']} "
                           f"(每 {website['interval_minutes']} 分钟){selector_info}{notifier_info}")

        try:
            while True:
                now = time.time()
                for website in self.config["websites"]:
                    if self.should_check(website, now):
                        self.check_website(website)
                        self.last_checked[website["name"]] = now
                time.sleep(5)
        except KeyboardInterrupt:
            self.logger.info("脚本已停止")


def main():
    parser = argparse.ArgumentParser(description="网页内容监控脚本")
    parser.add_argument(
        "-c", "--config", default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    args = parser.parse_args()

    monitor = WebsiteMonitor(args.config)
    monitor.run()


if __name__ == "__main__":
    main()
