"""Expose stable source HTML for the shared text-property binding."""
from PyQt6.QtWidgets import QTextBrowser


class LocalizedTextBrowser(QTextBrowser):
    def text(self):
        return getattr(self, "_source_html", "")

    def setText(self, html):
        position = self.verticalScrollBar().value()
        self._source_html = str(html)
        self.setHtml(self._source_html)
        self.verticalScrollBar().setValue(position)
