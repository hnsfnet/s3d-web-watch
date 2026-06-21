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
                    self._send_webhook(name, url, summary, report_path, event="website_changed")
                else:
                    self.logger.warning(f"未知的通知方式: {nname}")
            except Exception as e:
                self.logger.error(f"通知失败 [{nname}]: {e}")

    def send_alert(self, notifier_names, name, url, error_msg, failure_count):
        title = f"⚠️ 连续抓取失败告警 ({failure_count}次)"
        summary = f"{title}\n网页: {name}\nURL: {url}\n错误: {error_msg}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        for nname in notifier_names:
            try:
                if nname == "email":
                    self._send_alert_email(name, url, summary)
                elif nname == "wecom":
                    self._send_alert_wecom(name, url, error_msg, failure_count)
                elif nname == "webhook":
                    self._send_webhook(name, url, summary, None, event="website_failure",
                                       extra={"failure_count": failure_count, "error": error_msg})
                else:
                    self.logger.warning(f"未知的通知方式: {nname}")
            except Exception as e:
                self.logger.error(f"告警通知失败 [{nname}]: {e}")

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

        self._smtp_send(cfg, msg)
        self.logger.info("邮件通知已发送")

    def _send_alert_email(self, name, url, summary):
        cfg = self.config.get("notifiers", {}).get("email", {})
        if not cfg:
            return
        msg = MIMEMultipart()
        msg["From"] = cfg["sender"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg["Subject"] = f"[告警] {name} 连续抓取失败"
        msg.attach(MIMEText(summary, "plain", "utf-8"))
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
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        resp = requests.post(cfg["webhook_url"], json=payload, timeout=30)
        resp.raise_for_status()
        self.logger.info("企业微信通知已发送")

    def _send_alert_wecom(self, name, url, error_msg, failure_count):
        cfg = self.config.get("notifiers", {}).get("wecom", {})
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
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        resp = requests.post(cfg["webhook_url"], json=payload, timeout=30)
        resp.raise_for_status()
        self.logger.info("企业微信告警已发送")

    def _send_webhook(self, name, url, summary, report_path, event="website_changed", extra=None):
        cfg = self.config.get("notifiers", {}).get("webhook", {})
        if not cfg:
            return
        payload = {
            "event": event,
            "name": name,
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "report_path": report_path,
        }
        if extra:
            payload.update(extra)
        method = cfg.get("method", "POST").upper()
        headers = cfg.get("headers", {})
        resp = requests.request(method, cfg["url"], json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        self.logger.info(f"Webhook 通知已发送 ({event})")


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


class ContentProcessor:
    @staticmethod
    def extract_by_selector(html, selector=None):
        if not selector:
            return html
        try:
            soup = BeautifulSoup(html, "lxml")
            elements = soup.select(selector)
            if not elements:
                return ""
            return "\n".join(str(el) for el in elements)
        except Exception:
            return html

    @staticmethod
    def apply_ignore_patterns(content, patterns):
        if not patterns:
            return content
        result = content
        for pat in patterns:
            try:
                result = re.sub(pat, "", result, flags=re.MULTILINE)
            except re.error as e:
                pass
        return result


class WebsiteMonitor:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self.load_config()
        self.content_dir = self.config["settings"]["content_dir"]
        self.log_file = self.config["settings"]["log_file"]
        self.report_dir = self.config["settings"].get("report_dir", "reports")
        self.default_timeout = self.config["settings"].get("default_timeout_seconds", 30)
        self.max_failures = self.config["settings"].get("max_failures", 3)
        self.setup_logging()
        self.last_checked = {}
        self.failure_counts = {}
        self.alerted_failures = {}

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

    def get_snapshot_dir(self, name):
        return os.path.join(self.content_dir, self._safe_name(name))

    def get_hash_path(self, name):
        return os.path.join(self.content_dir, f"{self._safe_name(name)}.hash")

    def _save_snapshot(self, name, content, label):
        snap_dir = self.get_snapshot_dir(name)
        os.makedirs(snap_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(snap_dir, f"{label}_{timestamp}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _read_latest_snapshot(self, name):
        snap_dir = self.get_snapshot_dir(name)
        if not os.path.isdir(snap_dir):
            return None
        files = sorted([f for f in os.listdir(snap_dir) if f.endswith(".html")], reverse=True)
        if not files:
            return None
        latest = os.path.join(snap_dir, files[0])
        with open(latest, "r", encoding="utf-8") as f:
            return f.read()

    def fetch_content(self, url, timeout):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text, None
        except requests.RequestException as e:
            return None, str(e)

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

    def _handle_failure(self, website, error_msg):
        name = website["name"]
        count = self.failure_counts.get(name, 0) + 1
        self.failure_counts[name] = count
        self.logger.error(f"抓取失败 [{name}] 第 {count} 次: {error_msg}")

        if count >= self.max_failures and not self.alerted_failures.get(name, False):
            notifier_names = website.get("notifiers", [])
            if notifier_names:
                self.notifier.send_alert(notifier_names, name, website["url"], error_msg, count)
            self.alerted_failures[name] = True

    def _handle_success(self, website):
        name = website["name"]
        if self.failure_counts.get(name, 0) > 0:
            self.logger.info(f"[{name}] 已恢复正常抓取")
        self.failure_counts[name] = 0
        self.alerted_failures[name] = False

    def check_website(self, website):
        name = website["name"]
        url = website["url"]
        selector = website.get("selector")
        ignore_patterns = website.get("ignore_patterns", [])
        timeout = website.get("timeout_seconds", self.default_timeout)

        self.logger.info(f"检查: {name}" + (f" (selector: {selector})" if selector else ""))

        raw_html, error = self.fetch_content(url, timeout)
        if error:
            self._handle_failure(website, error)
            return

        extracted = ContentProcessor.extract_by_selector(raw_html, selector)
        if not extracted:
            self.logger.warning(f"内容为空，跳过: {name}")
            self._handle_failure(website, "CSS 选择器未匹配到内容或内容为空")
            return

        current_content = ContentProcessor.apply_ignore_patterns(extracted, ignore_patterns)
        current_hash = self.compute_hash(current_content)
        last_hash = self.read_last_hash(name)

        self._handle_success(website)

        if last_hash is None:
            self.logger.info(f"首次记录: {name}")
            self.save_hash(name, current_hash)
            self._save_snapshot(name, current_content, "initial")
            return

        if current_hash == last_hash:
            self.logger.info(f"无变化: {name}")
            return

        last_content = self._read_latest_snapshot(name) or ""
        self.log_change(name, url, last_content, current_content)

        self._save_snapshot(name, last_content, "old")
        self._save_snapshot(name, current_content, "new")
        report_path = self.reporter.generate(name, url, last_content, current_content)

        notifier_names = website.get("notifiers", [])
        if notifier_names:
            self.notifier.send(notifier_names, name, url, report_path, last_content, current_content)

        self.save_hash(name, current_hash)

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
        self.logger.info(f"默认超时: {self.default_timeout}s, 连续失败告警阈值: {self.max_failures}次")

        for website in self.config["websites"]:
            selector_info = f" [selector: {website.get('selector', '全部')}]"
            notifier_info = f" [通知: {', '.join(website.get('notifiers', [])) or '无'}]"
            timeout_info = f" [超时: {website.get('timeout_seconds', self.default_timeout)}s]"
            ignore_count = len(website.get('ignore_patterns', []))
            ignore_info = f" [忽略规则: {ignore_count}条]" if ignore_count else ""
            self.logger.info(f"  - {website['name']}: {website['url']} "
                           f"(每 {website['interval_minutes']} 分钟){selector_info}{notifier_info}{timeout_info}{ignore_info}")

        try:
            while True:
                now = time.time()
                for website in self.config["websites"]:
                    if self.should_check(website, now):
                        try:
                            self.check_website(website)
                        except Exception as e:
                            self.logger.error(f"检查异常 [{website['name']}]: {e}")
                        finally:
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
