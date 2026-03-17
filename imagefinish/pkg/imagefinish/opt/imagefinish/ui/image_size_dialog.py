from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QComboBox, QCheckBox,
    QDialogButtonBox, QFrame,
)
from PyQt6.QtCore import Qt
from core.locale import tr


class ImageSizeDialog(QDialog):

    _RESAMPLE = (
        ("image_size.nearest",  Qt.TransformationMode.FastTransformation),
        ("image_size.bilinear", Qt.TransformationMode.SmoothTransformation),
    )

    def __init__(self, width: int, height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("image_size.title"))
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        self._ratio    = width / height if height else 1.0
        self._updating = False

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # Current size
        current_lbl = QLabel(tr("image_size.current", w=width, h=height))
        current_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        current_lbl.setObjectName("dimInfo")
        root.addWidget(current_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Width / Height
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._w_spin = QSpinBox()
        self._w_spin.setRange(1, 16384)
        self._w_spin.setValue(width)
        self._w_spin.setSuffix(" px")
        form.addRow(tr("image_size.width"), self._w_spin)

        self._constrain = QCheckBox(tr("image_size.constrain"))
        self._constrain.setChecked(True)
        form.addRow("", self._constrain)

        self._h_spin = QSpinBox()
        self._h_spin.setRange(1, 16384)
        self._h_spin.setValue(height)
        self._h_spin.setSuffix(" px")
        form.addRow(tr("image_size.height"), self._h_spin)

        root.addLayout(form)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep2)

        # Resample
        resample_row = QHBoxLayout()
        resample_row.addWidget(QLabel(tr("image_size.resample")))
        self._resample_combo = QComboBox()
        for key, _ in self._RESAMPLE:
            self._resample_combo.addItem(tr(key))
        self._resample_combo.setCurrentIndex(1)
        resample_row.addWidget(self._resample_combo, 1)
        root.addLayout(resample_row)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._w_spin.valueChanged.connect(self._on_w_changed)
        self._h_spin.valueChanged.connect(self._on_h_changed)

    def _on_w_changed(self, w: int):
        if self._updating or not self._constrain.isChecked():
            return
        self._updating = True
        self._h_spin.setValue(max(1, round(w / self._ratio)))
        self._updating = False

    def _on_h_changed(self, h: int):
        if self._updating or not self._constrain.isChecked():
            return
        self._updating = True
        self._w_spin.setValue(max(1, round(h * self._ratio)))
        self._updating = False

    def result_size(self) -> tuple[int, int]:
        return self._w_spin.value(), self._h_spin.value()

    def result_transform(self) -> Qt.TransformationMode:
        i = self._resample_combo.currentIndex()
        return self._RESAMPLE[i][1] if 0 <= i < len(self._RESAMPLE) else Qt.TransformationMode.SmoothTransformation
