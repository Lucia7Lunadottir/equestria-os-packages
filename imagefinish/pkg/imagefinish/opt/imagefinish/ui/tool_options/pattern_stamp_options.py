import os
import glob
import shutil
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel, QFileDialog, QSlider, QSpinBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt
from .brush_options import BrushOptions
from core.locale import tr

class PatternStampOptions(BrushOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._pattern_combo = QComboBox()
        self._pattern_combo.setIconSize(QSize(32, 32))
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pat_dir = os.path.join(base_dir, "patterns")
        if os.path.exists(pat_dir):
            for ext in ('*.png', '*.jpg', '*.jpeg', '*.bmp'):
                for path in glob.glob(os.path.join(pat_dir, ext)):
                    name = os.path.splitext(os.path.basename(path))[0]
                    self._pattern_combo.addItem(QIcon(path), name, path)
                    
        self._pattern_combo.addItem(QIcon(), tr("opts.load"), "load_custom")
        self._pattern_combo.activated.connect(self._on_pattern_activated)
        
        pat_widget = QWidget()
        pat_layout = QHBoxLayout(pat_widget)
        pat_layout.setContentsMargins(0, 0, 0, 0)
        self._pat_lbl = QLabel(tr("opts.pattern"))
        pat_layout.addWidget(self._pat_lbl)
        pat_layout.addWidget(self._pattern_combo)
        
        # --- Масштаб узора ---
        self._scale_lbl = QLabel(tr("opts.pattern_scale"))
        pat_layout.addWidget(self._scale_lbl)
        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(1, 500)
        self._scale_slider.setFixedWidth(100)
        self._scale_spin = QSpinBox()
        self._scale_spin.setRange(1, 5000)
        self._scale_spin.setSuffix("%")
        self._scale_slider.valueChanged.connect(self._on_scale_slider_change)
        self._scale_spin.valueChanged.connect(self._on_scale_spin_change)
        pat_layout.addWidget(self._scale_slider)
        pat_layout.addWidget(self._scale_spin)

        # Добавляем в самое начало панели кисти
        self.layout.insertWidget(0, pat_widget)

    def _on_pattern_activated(self, idx):
        data = self._pattern_combo.itemData(idx)
        if data == "load_custom":
            path, _ = QFileDialog.getOpenFileName(self, tr("opts.pattern_select"), "", "Images (*.png *.jpg *.jpeg *.bmp)")
            if path:
                filename = os.path.basename(path)
                name = os.path.splitext(filename)[0]
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                pat_dir = os.path.join(base_dir, "patterns")
                os.makedirs(pat_dir, exist_ok=True)
                target_path = os.path.join(pat_dir, filename)
                if path != target_path: shutil.copy2(path, target_path)
                
                new_idx = self._pattern_combo.count() - 1
                self._pattern_combo.insertItem(new_idx, QIcon(target_path), name, target_path)
                self._pattern_combo.setCurrentIndex(new_idx)
                self.option_changed.emit("brush_pattern", target_path)
            else:
                self._pattern_combo.setCurrentIndex(0)
                self.option_changed.emit("brush_pattern", self._pattern_combo.itemData(0))
        else:
            self.option_changed.emit("brush_pattern", data)

    def add_custom_pattern(self, path, name):
        new_idx = self._pattern_combo.count() - 1
        self._pattern_combo.insertItem(new_idx, QIcon(path), name, path)
        self._pattern_combo.setCurrentIndex(new_idx)
        self.option_changed.emit("brush_pattern", path)

    def _on_scale_slider_change(self, value):
        self._scale_spin.blockSignals(True)
        self._scale_spin.setValue(value)
        self._scale_spin.blockSignals(False)
        self.option_changed.emit("brush_pattern_scale", value)

    def _on_scale_spin_change(self, value):
        self._scale_slider.blockSignals(True)
        self._scale_slider.setValue(value)
        self._scale_slider.blockSignals(False)
        self.option_changed.emit("brush_pattern_scale", value)

    def update_from_opts(self, opts: dict):
        super().update_from_opts(opts)
        self._scale_slider.blockSignals(True)
        self._scale_spin.blockSignals(True)
        
        scale = opts.get("brush_pattern_scale", 100)
        self._scale_slider.setValue(scale)
        self._scale_spin.setValue(scale)
        
        self._scale_slider.blockSignals(False)
        self._scale_spin.blockSignals(False)

    def retranslate(self):
        super().retranslate()
        self._pat_lbl.setText(tr("opts.pattern"))
        self._scale_lbl.setText(tr("opts.pattern_scale"))
        self._pattern_combo.setItemText(self._pattern_combo.count() - 1, tr("opts.load"))