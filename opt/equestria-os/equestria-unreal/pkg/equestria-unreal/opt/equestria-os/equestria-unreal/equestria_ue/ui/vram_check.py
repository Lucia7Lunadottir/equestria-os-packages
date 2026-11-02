from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from equestria_ue import gpu_memory
from equestria_ue.kit import tr


def confirm_launch(parent) -> bool:
    """Перед запуском редактора: хватит ли видеопамяти. Ничего не закрывает —
    только показывает, кто её занимает, и спрашивает, запускать ли."""
    report = gpu_memory.query()
    if report is None or report.enough:
        return True
    top = "\n".join(f"  • {name} — {mib / 1024:.1f} " + tr("ГБ") for name, mib in report.consumers[:6])
    text = tr("Свободно {} ГБ видеопамяти из {}. Редактору Unreal с Lumen и трассировкой лучей нужно около {} ГБ — "
              "иначе он падает с нехваткой видеопамяти.",
              f"{report.free_mib / 1024:.1f}", f"{report.total_mib / 1024:.0f}", f"{gpu_memory.NEEDED_MIB / 1024:.0f}")
    if top:
        text += "\n\n" + tr("Сейчас видеопамять занимают:") + "\n" + top
    text += "\n\n" + tr("Закройте ненужные программы или выключите трассировку лучей в настройках лаунчера.")
    box = QMessageBox(QMessageBox.Icon.Warning, tr("Мало видеопамяти"), text, parent=parent)
    run = box.addButton(tr("Запустить всё равно"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    return box.clickedButton() is run
