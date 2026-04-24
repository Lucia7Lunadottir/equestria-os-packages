from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QLineEdit, QProgressBar
)
from PyQt6.QtCore import Qt


class Ui_Relocator:
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(640, 540)

        self.root = QWidget(MainWindow)
        self.root.setObjectName("root")
        MainWindow.setCentralWidget(self.root)

        main_layout = QVBoxLayout(self.root)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(12)

        # --- App title + lang row ---
        title_row = QHBoxLayout()
        self.app_title = QLabel("Relocate Files")
        self.app_title.setObjectName("AppTitle")
        title_row.addWidget(self.app_title)
        title_row.addStretch()
        self.lang_row = QHBoxLayout()
        self.lang_row.setSpacing(4)
        title_row.addLayout(self.lang_row)
        main_layout.addLayout(title_row)

        # --- Divider ---
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        main_layout.addWidget(divider)

        # --- Sources section ---
        self.sources_label = QLabel("Source(s)")
        self.sources_label.setObjectName("SectionLabel")
        main_layout.addWidget(self.sources_label)

        self.source_scroll = QScrollArea()
        self.source_scroll.setObjectName("SourceScrollArea")
        self.source_scroll.setWidgetResizable(True)
        self.source_scroll.setMaximumHeight(200)

        self.source_container = QWidget()
        self.source_container.setObjectName("SourceContainer")
        self.source_rows_layout = QVBoxLayout(self.source_container)
        self.source_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.source_rows_layout.setSpacing(6)
        self.source_rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.source_scroll.setWidget(self.source_container)
        main_layout.addWidget(self.source_scroll)

        self.add_source_btn = QPushButton("+ Add Source")
        self.add_source_btn.setObjectName("AddSourceBtn")
        self.add_source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        main_layout.addWidget(self.add_source_btn)

        # --- Destination section ---
        self.dest_label = QLabel("Destination")
        self.dest_label.setObjectName("SectionLabel")
        main_layout.addWidget(self.dest_label)

        dest_row = QHBoxLayout()
        self.dest_edit = QLineEdit()
        self.dest_edit.setObjectName("DestEdit")
        self.dest_edit.setPlaceholderText("Select destination folder…")
        self.dest_browse_btn = QPushButton("Browse…")
        self.dest_browse_btn.setObjectName("BrowseBtn")
        self.dest_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dest_row.addWidget(self.dest_edit)
        dest_row.addWidget(self.dest_browse_btn)
        main_layout.addLayout(dest_row)

        # --- NTFS warning ---
        self.ntfs_warning = QLabel(
            "⚠  Symlinks are not supported on NTFS. The file will be moved without a symlink."
        )
        self.ntfs_warning.setObjectName("NtfsWarning")
        self.ntfs_warning.setWordWrap(True)
        self.ntfs_warning.hide()
        main_layout.addWidget(self.ntfs_warning)

        # --- Relocate button ---
        self.relocate_btn = QPushButton("Relocate")
        self.relocate_btn.setObjectName("RelocateBtn")
        self.relocate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        main_layout.addWidget(self.relocate_btn)

        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ProgressBar")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # --- Status label ---
        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()
