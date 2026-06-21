import os
import re
import difflib
from datetime import datetime


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
