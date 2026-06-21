import pkgutil
import importlib

from .base import BaseNotifier, register, build_notifier, available_notifiers

for _, module_name, _ in pkgutil.iter_modules(__path__):
    if module_name.endswith("_notifier"):
        importlib.import_module(f".{module_name}", __name__)


class NotifierManager:
    def __init__(self, app_config, logger):
        self.notifiers_config = app_config.notifiers_config
        self.logger = logger

    def send(self, notifier_names, name, url, summary, report_path):
        for nname in notifier_names:
            notifier = build_notifier(nname, self.notifiers_config, self.logger)
            if notifier is None:
                self.logger.warning(f"未知的通知方式: {nname}")
                continue
            try:
                notifier.send_change(name, url, summary, report_path)
            except Exception as e:
                self.logger.error(f"通知失败 [{nname}]: {e}")

    def send_alert(self, notifier_names, name, url, error_msg, failure_count):
        for nname in notifier_names:
            notifier = build_notifier(nname, self.notifiers_config, self.logger)
            if notifier is None:
                self.logger.warning(f"未知的通知方式: {nname}")
                continue
            try:
                notifier.send_alert(name, url, error_msg, failure_count)
            except Exception as e:
                self.logger.error(f"告警通知失败 [{nname}]: {e}")
