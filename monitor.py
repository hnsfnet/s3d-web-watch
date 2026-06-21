#!/usr/bin/env python3
import os
import time
import hashlib
import logging
import argparse
from datetime import datetime

import requests
import yaml


class WebsiteMonitor:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self.load_config()
        self.content_dir = self.config["settings"]["content_dir"]
        self.log_file = self.config["settings"]["log_file"]
        self.setup_logging()
        self.last_checked = {}

        os.makedirs(self.content_dir, exist_ok=True)

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

    def get_content_path(self, name):
        safe_name = name.replace(" ", "_").replace("/", "_")
        return os.path.join(self.content_dir, f"{safe_name}.html")

    def get_hash_path(self, name):
        safe_name = name.replace(" ", "_").replace("/", "_")
        return os.path.join(self.content_dir, f"{safe_name}.hash")

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

        self.logger.info(f"检查: {name}")

        current_content = self.fetch_content(url)
        if current_content is None:
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
            self.logger.info(f"  - {website['name']}: {website['url']} "
                           f"(每 {website['interval_minutes']} 分钟)")

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
