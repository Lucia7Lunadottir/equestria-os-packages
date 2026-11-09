from __future__ import annotations

from equestria_kit import live_i18n

from PyQt6.QtWidgets import QMessageBox

from equestria_ue import gpu_memory
from equestria_ue.kit import tr


def confirm_launch(parent) -> bool:
    """Перед запуском редактора: хватит ли видеопамяти. Ничего не закрывает —
    только показывает, кто её занимает, и спрашивает, запускать ли."""
    report = gpu_memory.query()
    if report is None or report.enough:
        return True
    top = "\n".join(f"  • {name} — {mib / 1024:.1f} " + tr("common.gb") for name, mib in report.consumers[:6])
    text = tr("vram_check.gb_gb_video_memory_free",
              f"{report.free_mib / 1024:.1f}", f"{report.total_mib / 1024:.0f}", f"{gpu_memory.NEEDED_MIB / 1024:.0f}")
    if top:
        text += "\n\n" + tr("vram_check.video_memory_currently_used_by") + "\n" + top
    text += "\n\n" + tr("vram_check.close_apps_you_don_t")
    box = QMessageBox(QMessageBox.Icon.Warning, tr("vram_check.low_video_memory"), text, parent=parent)
    run = live_i18n.call(box.addButton, tr("vram_check.launch_anyway"), QMessageBox.ButtonRole.AcceptRole)
    live_i18n.call(box.addButton, QMessageBox.StandardButton.Cancel)
    box.exec()
    return box.clickedButton() is run
