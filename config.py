import logging

import yaml


class WebsiteConfig:
    def __init__(self, data):
        self.name = data["name"]
        self.url = data["url"]
        self.interval_minutes = data["interval_minutes"]
        self.selector = data.get("selector")
        self.ignore_patterns = data.get("ignore_patterns", [])
        self.timeout_seconds = data.get("timeout_seconds")
        self.notifiers = data.get("notifiers", [])

    @property
    def interval_seconds(self):
        return self.interval_minutes * 60

    def effective_timeout(self, default):
        return self.timeout_seconds if self.timeout_seconds is not None else default


class AppConfig:
    def __init__(self, data):
        settings = data.get("settings", {})
        self.log_file = settings.get("log_file", "changes.log")
        self.content_dir = settings["content_dir"]
        self.report_dir = settings.get("report_dir", "reports")
        self.default_timeout = settings.get("default_timeout_seconds", 30)
        self.max_failures = settings.get("max_failures", 3)
        self.notifiers_config = data.get("notifiers", {})
        self.websites = [WebsiteConfig(w) for w in data.get("websites", [])]


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppConfig(data)


def setup_logger(log_file):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("monitor")
