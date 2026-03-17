from PyQt6.QtWidgets import QPushButton
from .base_options import BaseOptions
from core.locale import tr

class PenOptions(BaseOptions):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hint = self._lbl("opts.pen_hint")
        self.layout.addWidget(self._hint)
        
        self.layout.addSpacing(15)
        
        self._btn_sel = QPushButton(tr("opts.pen.selection"))
        self._btn_sel.setObjectName("smallBtn")
        self._btn_sel.clicked.connect(lambda: self.option_changed.emit("pen_action", "selection"))
        
        self._btn_shape = QPushButton(tr("opts.pen.shape"))
        self._btn_shape.setObjectName("smallBtn")
        self._btn_shape.clicked.connect(lambda: self.option_changed.emit("pen_action", "shape"))
        
        self._btn_clear = QPushButton(tr("opts.pen.clear"))
        self._btn_clear.setObjectName("smallBtn")
        self._btn_clear.clicked.connect(lambda: self.option_changed.emit("pen_action", "clear"))
        
        self.layout.addWidget(self._btn_sel)
        self.layout.addWidget(self._btn_shape)
        self.layout.addWidget(self._btn_clear)
        self.layout.addStretch()

    def retranslate(self):
        self._hint.setText(tr("opts.pen_hint"))
        self._btn_sel.setText(tr("opts.pen.selection"))
        self._btn_shape.setText(tr("opts.pen.shape"))
        self._btn_clear.setText(tr("opts.pen.clear"))
        super().retranslate()