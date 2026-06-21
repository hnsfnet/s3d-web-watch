from abc import ABC, abstractmethod


_REGISTRY = {}


class BaseNotifier(ABC):
    notifier_name = None

    def __init__(self, notifiers_config, logger):
        self.notifiers_config = notifiers_config
        self.logger = logger

    @property
    def cfg(self):
        return self.notifiers_config.get(self.notifier_name, {})

    @abstractmethod
    def send_change(self, name, url, summary, report_path):
        raise NotImplementedError

    @abstractmethod
    def send_alert(self, name, url, error_msg, failure_count):
        raise NotImplementedError


def register(name):
    def decorator(cls):
        cls.notifier_name = name
        _REGISTRY[name] = cls
        return cls
    return decorator


def build_notifier(name, notifiers_config, logger):
    cls = _REGISTRY.get(name)
    if cls is None:
        return None
    return cls(notifiers_config, logger)


def available_notifiers():
    return list(_REGISTRY.keys())
