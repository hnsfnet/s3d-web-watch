#!/usr/bin/env python3
import time
import argparse

from config import load_config, setup_logger
from fetcher import WebFetcher
from comparator import ContentComparator, CompareResult
from reporter import DiffReporter
from notifiers import NotifierManager


class WebsiteMonitor:
    def __init__(self, config_path):
        self.config = load_config(config_path)
        self.logger = setup_logger(self.config.log_file)
        self.fetcher = WebFetcher(self.logger)
        self.comparator = ContentComparator(self.config.content_dir, self.logger)
        self.reporter = DiffReporter(self.config.report_dir, self.logger)
        self.notifier = NotifierManager(self.config, self.logger)
        self.last_checked = {}
        self.failure_counts = {}
        self.alerted_failures = {}

    def _handle_failure(self, website, error_msg):
        name = website.name
        count = self.failure_counts.get(name, 0) + 1
        self.failure_counts[name] = count
        self.logger.error(f"抓取失败 [{name}] 第 {count} 次: {error_msg}")

        if count >= self.config.max_failures and not self.alerted_failures.get(name, False):
            if website.notifiers:
                self.notifier.send_alert(website.notifiers, name, website.url, error_msg, count)
            self.alerted_failures[name] = True

    def _handle_success(self, website):
        name = website.name
        if self.failure_counts.get(name, 0) > 0:
            self.logger.info(f"[{name}] 已恢复正常抓取")
        self.failure_counts[name] = 0
        self.alerted_failures[name] = False

    def check_website(self, website):
        name = website.name
        timeout = website.effective_timeout(self.config.default_timeout)
        self.logger.info(f"检查: {name}" + (f" (selector: {website.selector})" if website.selector else ""))

        raw_html, error = self.fetcher.fetch(website.url, timeout)
        if error:
            self._handle_failure(website, error)
            return

        content = self.comparator.prepare(raw_html, website.selector, website.ignore_patterns)
        if not content:
            self.logger.warning(f"内容为空，跳过: {name}")
            self._handle_failure(website, "CSS 选择器未匹配到内容或内容为空")
            return

        self._handle_success(website)

        result = self.comparator.compare(name, content)

        if result.status == CompareResult.NEW:
            self.logger.info(f"首次记录: {name}")
        elif result.status == CompareResult.UNCHANGED:
            self.logger.info(f"无变化: {name}")
        elif result.status == CompareResult.CHANGED:
            self.logger.info(
                self.comparator.format_change_log(name, website.url, result.old_content, result.new_content)
            )
            report_path = self.reporter.generate(
                name, website.url, result.old_content, result.new_content
            )
            if website.notifiers:
                summary = self.comparator.build_summary(result.old_content, result.new_content)
                self.notifier.send(website.notifiers, name, website.url, summary, report_path)

    def should_check(self, website, now):
        last_check = self.last_checked.get(website.name, 0)
        return now - last_check >= website.interval_seconds

    def run(self):
        self.logger.info("网页内容监控脚本启动")
        self.logger.info(f"监控 {len(self.config.websites)} 个网页")
        self.logger.info(
            f"默认超时: {self.config.default_timeout}s, 连续失败告警阈值: {self.config.max_failures}次"
        )

        for website in self.config.websites:
            selector_info = f" [selector: {website.selector or '全部'}]"
            notifier_info = f" [通知: {', '.join(website.notifiers) or '无'}]"
            timeout_info = f" [超时: {website.effective_timeout(self.config.default_timeout)}s]"
            ignore_count = len(website.ignore_patterns)
            ignore_info = f" [忽略规则: {ignore_count}条]" if ignore_count else ""
            self.logger.info(
                f"  - {website.name}: {website.url} "
                f"(每 {website.interval_minutes} 分钟){selector_info}{notifier_info}{timeout_info}{ignore_info}"
            )

        try:
            while True:
                now = time.time()
                for website in self.config.websites:
                    if self.should_check(website, now):
                        try:
                            self.check_website(website)
                        except Exception as e:
                            self.logger.error(f"检查异常 [{website.name}]: {e}")
                        finally:
                            self.last_checked[website.name] = now
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
