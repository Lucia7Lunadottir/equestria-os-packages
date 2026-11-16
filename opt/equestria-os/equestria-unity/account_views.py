"""Cards for the Unity ID and its licenses, laid out like Unity Hub. They only draw an AccountState."""
import re

from PyQt6.QtCore import QDate, QLocale, Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from controls import chip, tile
from kit import call, tr

LICENSE_TYPES = {"assigned": "license.type_assigned"}  # other types are shown as the CLI names them


def initials(text):
    """Two letters for a badge: "Unity Personal" -> PE, "Asset Store" -> AS."""
    words = [w for w in re.split(r"[\s._@-]+", text) if w and w.casefold() != "unity"]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def long_date(text):
    date = QDate.fromString(text[:10], Qt.DateFormat.ISODate)
    return QLocale().toString(date, QLocale.FormatType.LongFormat) if date.isValid() else text


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class LicenseCard(QFrame):
    """One license: a badge on the left, the product and its details on the right."""

    def __init__(self, entry, count):
        super().__init__()
        self.setObjectName("licenseCard")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        badge = QLabel(initials(str(entry["product"])))
        badge.setObjectName("licenseBadge")
        badge.setFixedWidth(96)
        badge.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        row.addWidget(badge)
        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 16)
        body.setSpacing(8)
        head = QHBoxLayout()
        name = QLabel(str(entry["product"]))
        name.setObjectName("rowname")
        head.addWidget(name)
        if count > 1:
            head.addWidget(chip(f"×{count}"))
        head.addStretch()
        body.addLayout(head)
        details = QGridLayout()
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(4)
        kind = str(entry.get("type") or "")
        expires = str(entry.get("expires") or "")
        rows = [("license.type", tr(LICENSE_TYPES[kind.casefold()]) if kind.casefold() in LICENSE_TYPES else kind),
                ("license.organization", str(entry.get("organization") or "")),
                ("license.expires", long_date(expires) if expires else tr("license.no_expiry"))]
        for line, (key, value) in enumerate((key, value) for key, value in rows if value):
            label = call(QLabel, tr(key))
            label.setObjectName("hint")
            details.addWidget(label, line, 0)
            details.addWidget(call(QLabel, value), line, 1)
        details.setColumnStretch(1, 1)
        body.addLayout(details)
        body.addStretch()
        row.addLayout(body, 1)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)


class LicenseList(QWidget):
    """Every active license as a card, or why there is nothing to show."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(10)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        state.changed.connect(self.redraw)
        self.redraw()

    def redraw(self):
        clear(self.box)
        problem = self.state.problems["license"]
        licenses = self.state.licenses()
        if licenses:
            for entry, count in licenses:
                self.box.addWidget(LicenseCard(entry, count))
        else:
            if problem:
                text = problem
            elif "license" in self.state.loading:
                text = tr("account.loading")
            else:
                text = tr("license.none")
            note = call(QLabel, text)
            note.setObjectName("err" if problem else "hint")
            note.setWordWrap(True)
            self.box.addWidget(note)


class AccountCard(QFrame):
    """The signed-in Unity ID: avatar with initials, name, e-mail and sign-in state."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.state = state
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(14)
        self.avatar = QLabel()
        self.avatar.setFixedSize(56, 56)
        row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        top = QHBoxLayout()
        self.name = QLabel()
        self.name.setObjectName("rowname")
        top.addWidget(self.name)
        self.status = chip("")
        top.addWidget(self.status)
        top.addStretch()
        column.addLayout(top)
        self.email = QLabel()
        self.email.setObjectName("hint")
        self.email.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.email)
        self.problem = QLabel()
        self.problem.setObjectName("err")
        self.problem.setWordWrap(True)
        column.addWidget(self.problem)
        row.addLayout(column, 1)
        state.changed.connect(self.redraw)
        self.redraw()

    def redraw(self):
        user = self.state.user()
        signed_in = self.state.signed_in()
        name = str(user.get("name") or "")
        self.avatar.setPixmap(tile(initials(name) if signed_in and name else "?", name or "?", 56, 56, 28))
        if signed_in:
            self.name.setText(name or str(user.get("email") or ""))
        else:
            call(self.name.setText, tr("account.loading" if "auth" in self.state.loading else "account.signed_out"))
        self.email.setText(str(user.get("email") or "") if signed_in else "")
        self.email.setVisible(signed_in)
        call(self.status.setText, tr("account.signed_in"))
        self.status.setProperty("lvl", "ok")
        self.status.setVisible(signed_in)
        problem = self.state.problems["auth"]
        if problem:
            call(self.problem.setText, problem)
        else:
            self.problem.clear()
        self.problem.setVisible(bool(problem))
