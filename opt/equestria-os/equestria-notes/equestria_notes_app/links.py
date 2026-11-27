"""notes: адреса в тексте — найти и превратить в ссылки."""
from __future__ import annotations

import re
from dataclasses import dataclass

# http(s)://…, mailto:…, www.… — до пробела или кавычки/угловой скобки
_URL_RE = re.compile(r"(?:https?://|mailto:|www\.)[^\s<>\"'«»]+", re.IGNORECASE)
_TRAILING = ".,;:!?…»”’'"


@dataclass(frozen=True)
class FoundLink:
    start: int      # позиция в строке
    end: int
    href: str       # куда ведёт (www. → https://www.)


class LinkFinder:
    """Ищет адреса в строке текста. Знаки препинания в конце («см. https://kde.org.»)
    и непарная закрывающая скобка («(https://kde.org)») в адрес не входят."""

    def find(self, text: str) -> list[FoundLink]:
        found = []
        for m in _URL_RE.finditer(text):
            url = self._trim(m.group(0))
            if len(url) <= len("https://") or url.lower() in ("www.", "mailto:"):
                continue
            href = "https://" + url if url.lower().startswith("www.") else url
            found.append(FoundLink(m.start(), m.start() + len(url), href))
        return found

    def at(self, text: str, pos: int) -> FoundLink | None:
        """Адрес, внутри которого стоит позиция pos, или None."""
        return next((f for f in self.find(text) if f.start <= pos < f.end), None)

    @staticmethod
    def _trim(url: str) -> str:
        while url:
            last = url[-1]
            if last in _TRAILING:
                url = url[:-1]
            elif last == ")" and url.count("(") < url.count(")"):
                url = url[:-1]
            else:
                break
        return url
