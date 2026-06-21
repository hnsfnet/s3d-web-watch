import os
import re
import hashlib
import difflib
from datetime import datetime

from bs4 import BeautifulSoup


class CompareResult:
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"

    def __init__(self, status, old_content=None, new_content=None):
        self.status = status
        self.old_content = old_content
        self.new_content = new_content


class ContentComparator:
    def __init__(self, content_dir, logger):
        self.content_dir = content_dir
        self.logger = logger
        os.makedirs(self.content_dir, exist_ok=True)

    def _safe_name(self, name):
        return name.replace(" ", "_").replace("/", "_")

    def _hash_path(self, name):
        return os.path.join(self.content_dir, f"{self._safe_name(name)}.hash")

    def _snapshot_dir(self, name):
        return os.path.join(self.content_dir, self._safe_name(name))

    def prepare(self, raw_html, selector=None, ignore_patterns=None):
        content = self._extract_by_selector(raw_html, selector)
        content = self._apply_ignore_patterns(content, ignore_patterns or [])
        return content

    def _extract_by_selector(self, html, selector):
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

    def _apply_ignore_patterns(self, content, patterns):
        result = content
        for pat in patterns:
            try:
                result = re.sub(pat, "", result, flags=re.MULTILINE)
            except re.error:
                pass
        return result

    def _compute_hash(self, content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_last_hash(self, name):
        path = self._hash_path(name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def _save_hash(self, name, content_hash):
        with open(self._hash_path(name), "w", encoding="utf-8") as f:
            f.write(content_hash)

    def _save_snapshot(self, name, content, label):
        snap_dir = self._snapshot_dir(name)
        os.makedirs(snap_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(snap_dir, f"{label}_{timestamp}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _read_latest_snapshot(self, name):
        snap_dir = self._snapshot_dir(name)
        if not os.path.isdir(snap_dir):
            return None
        files = sorted([f for f in os.listdir(snap_dir) if f.endswith(".html")], reverse=True)
        if not files:
            return None
        latest = os.path.join(snap_dir, files[0])
        with open(latest, "r", encoding="utf-8") as f:
            return f.read()

    def compare(self, name, content):
        current_hash = self._compute_hash(content)
        last_hash = self._read_last_hash(name)

        if last_hash is None:
            self._save_hash(name, current_hash)
            self._save_snapshot(name, content, "initial")
            return CompareResult(CompareResult.NEW, new_content=content)

        if current_hash == last_hash:
            return CompareResult(CompareResult.UNCHANGED)

        old_content = self._read_latest_snapshot(name) or ""
        self._save_snapshot(name, content, "snapshot")
        self._save_hash(name, current_hash)
        return CompareResult(CompareResult.CHANGED, old_content=old_content, new_content=content)

    def build_summary(self, old_content, new_content):
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

    def format_change_log(self, name, url, old_content, new_content):
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
        return log_entry
