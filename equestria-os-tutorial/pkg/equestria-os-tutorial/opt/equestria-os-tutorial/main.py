import sys
import os
import json
import subprocess
import glob
import shlex
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QStackedWidget, QTextBrowser, QLabel,
                             QGraphicsDropShadowEffect, QSizePolicy)
from PyQt6.QtGui import QFontDatabase, QFont, QPixmap, QPainter, QPainterPath, QColor, QIcon
from PyQt6.QtCore import Qt

class RoundedImageLabel(QLabel):
    """QLabel с закруглёнными краями, масштабирует изображение динамически."""
    def __init__(self, pixmap: QPixmap, radius: int = 16, max_h: int = 480, parent=None):
        super().__init__(parent)
        self._original = pixmap
        self._radius = radius
        self.setMaximumHeight(max_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def hasHeightForWidth(self):
        return not self._original.isNull()

    def heightForWidth(self, width: int) -> int:
        if self._original.isNull() or self._original.width() == 0:
            return 0
        return min(int(width * self._original.height() / self._original.width()), self.maximumHeight())

    def paintEvent(self, event):
        if self._original.isNull():
            return
        scaled = self._original.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), float(scaled.width()), float(scaled.height()),
                            float(self._radius), float(self._radius))
        painter.setClipPath(path)
        painter.drawPixmap(x, y, scaled)


class TutorialApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Equestria OS — Interactive Tour")
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tutorial.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        # --- Динамическая локализация ---
        self.locales_dir = os.path.join(self.base_path, "locales")
        self.langs = []
        self.translations = {}
        self.current_lang = "ru"
        self.load_translations()

        # Загрузка шрифта
        self.custom_font_family = "sans-serif"
        font_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.custom_font_family = families[0]

        # --- КОНФИГУРАЦИЯ СЛАЙДОВ ---
        self.slides_config = [
            # Шаг 0: Вводный
            {"title": "slide0_title", "text": "slide0_text", "image": "slide0.png", "actions": []},

            # Шаг 1: Навигация
            {"title": "slide1_title", "text": "slide1_text", "image": "slide1.png", "actions": []},

            # Шаг 2: Внешний вид
            {"title": "slide2_title", "text": "slide2_text", "image": "slide2.png", "actions": [
                {"btn": "s2_btn1", "desktop": "equestria-theme-switcher.desktop"},
                {"btn": "s2_btn2", "desktop": "equestria-os-task-panel-changer.desktop"}
            ]},

            # Шаг 3: Программы и Обновления (ТОЛЬКО ESSENTIALS)
            {"title": "slide3_title", "text": "slide3_text", "image": "slide3.png", "actions": [
                {"btn": "s3_btn1", "desktop": "equestria-app-store.desktop"}
            ]},

            # Шаг 4: Удаление пакетов
            {"title": "slide4_title", "text": "slide4_text", "image": "slide4.png", "actions": [
                {"btn": "s4_btn1", "desktop": "equestria-os-package-manager.desktop"}
            ]},

            # Шаг 5: Перенос файлов (Relocator)
            {"title": "slide5_title", "text": "slide5_text", "image": "slide5.png", "actions": [
                {"btn": "s5_btn1", "desktop": "equestria-os-relocator.desktop"}
            ]},

            # Шаг 6: Сервисы и Подкачка
            {"title": "slide6_title", "text": "slide6_text", "image": "slide6.png", "actions": [
                {"btn": "s6_btn1", "desktop": "equestria-os-services-manager.desktop"},
                {"btn": "s6_btn2", "desktop": "equestria-os-swap-manager.desktop"}
            ]},

            # Шаг 7: Финал (Welcome Hub)
            {"title": "slide7_title", "text": "slide7_text", "image": "slide7.png", "actions": [
                {"btn": "s7_btn1", "desktop": "equestria-os-welcome.desktop"}
            ]},
        ]

        self.current_slide = 0
        self.slides_data = [] # Храним ссылки на виджеты для смены языка на лету

        self.init_ui()
        self.load_stylesheet()
        self.update_ui_texts()

    def load_translations(self):
        if not os.path.exists(self.locales_dir):
            os.makedirs(self.locales_dir, exist_ok=True)
            return

        for file_path in glob.glob(os.path.join(self.locales_dir, "*.json")):
            lang_code = os.path.basename(file_path).replace(".json", "")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.translations[lang_code] = json.load(f)
                    self.langs.append(lang_code)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        self.langs.sort()
        if "ru" not in self.langs and self.langs:
            self.current_lang = self.langs[0]

    def t(self, key):
        lang_dict = self.translations.get(self.current_lang, {})
        en_dict = self.translations.get("en", {})
        return lang_dict.get(key, en_dict.get(key, f"[{key}]"))

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- ВЕРХНЯЯ ПАНЕЛЬ С ЯЗЫКАМИ ---
        self.top_bar = QWidget()
        self.top_bar.setObjectName("TopBar")
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(15, 10, 15, 10)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("LogoLabel")
        self.top_layout.addWidget(self.logo_label)

        self.top_layout.addStretch()

        self.lang_buttons = {}
        for lang in self.langs:
            btn = QPushButton(lang.upper())
            btn.setObjectName("LangBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, l=lang: self.change_language(l))
            self.lang_buttons[lang] = btn
            self.top_layout.addWidget(btn)

        self.main_layout.addWidget(self.top_bar)

        # --- ОБЛАСТЬ СЛАЙДОВ ---
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("ContentArea")
        self.main_layout.addWidget(self.content_area, 1)

        for config in self.slides_config:
            self.create_slide(config)

        # --- НИЖНЯЯ ПАНЕЛЬ (НАВИГАЦИЯ) ---
        self.bottom_bar = QWidget()
        self.bottom_bar.setObjectName("BottomBar")
        self.bottom_layout = QHBoxLayout(self.bottom_bar)
        self.bottom_layout.setContentsMargins(30, 15, 30, 20)

        self.btn_prev = QPushButton("← Back")
        self.btn_prev.setObjectName("NavBtnPrev")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self.go_prev)
        self.bottom_layout.addWidget(self.btn_prev)

        self.bottom_layout.addStretch()

        self.dots_layout = QHBoxLayout()
        self.dots_layout.setSpacing(8)
        self.dots = []
        for i in range(len(self.slides_config)):
            dot = QLabel("●")
            dot.setObjectName("ProgressDot")
            self.dots.append(dot)
            self.dots_layout.addWidget(dot)
        self.bottom_layout.addLayout(self.dots_layout)

        self.bottom_layout.addStretch()

        self.btn_next = QPushButton("Next ➔")
        self.btn_next.setObjectName("NavBtnNext")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self.go_next)
        self.bottom_layout.addWidget(self.btn_next)

        self.main_layout.addWidget(self.bottom_bar)
        self.update_navigation_state()

    def create_slide(self, config):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 20, 50, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Показ картинки, если она есть
        img_filename = config.get("image", "")
        img_path = os.path.join(self.base_path, "assets", img_filename)
        if os.path.exists(img_path) and img_filename:
            pixmap = QPixmap(img_path)
            img_label = RoundedImageLabel(pixmap, radius=14)

            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 100))
            img_label.setGraphicsEffect(shadow)

            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addStretch()
            wrapper_layout.addWidget(img_label)
            wrapper_layout.addStretch()
            layout.addWidget(wrapper)
            layout.addSpacing(15)

        # 2. Заголовок
        title = QLabel()
        title.setObjectName("SlideTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(10)

        # 3. Текст
        text = QTextBrowser()
        text.setObjectName("SlideText")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)

        # 4. Динамические кнопки
        slide_buttons = []
        actions = config.get("actions", [])
        if actions:
            layout.addSpacing(20)
            btn_container = QHBoxLayout()
            btn_container.addStretch()

            for act in actions:
                btn = QPushButton()
                btn.setObjectName("ActionBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # Биндим функцию запуска приложения
                btn.clicked.connect(lambda checked, t=act["desktop"]: self.launch_app(t))
                btn_container.addWidget(btn)
                slide_buttons.append({"widget": btn, "key": act["btn"]})

            btn_container.addStretch()
            layout.addLayout(btn_container)

        self.content_area.addWidget(page)

        self.slides_data.append({
            "title_widget": title, "title_key": config["title"],
            "text_widget": text, "text_key": config["text"],
            "buttons": slide_buttons
        })

    def launch_app(self, desktop_filename):
        """Умный запуск .desktop файла с парсингом Exec и отвязкой от терминала"""
        path = f"/usr/share/applications/{desktop_filename}"
        if not os.path.exists(path):
            print(f"File not found: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("Exec="):
                        cmd = line.strip().split("=", 1)[1]

                        # Удаляем плейсхолдеры запуска (%F, %U и т.д.)
                        for placeholder in ['%F', '%f', '%U', '%u', '%c', '%k']:
                            cmd = cmd.replace(placeholder, '')

                        cmd = cmd.strip()
                        # start_new_session=True отвязывает программу от окна туториала
                        subprocess.Popen(shlex.split(cmd), start_new_session=True)
                        return

        except Exception as e:
            print(f"Error launching {desktop_filename}: {e}")

        # Запасной вариант для KDE, если парсинг не удался
        subprocess.Popen(["kioclient", "exec", path])

    def go_next(self):
        if self.current_slide < len(self.slides_config) - 1:
            self.current_slide += 1
            self.update_navigation_state()
        else:
            self.close()

    def go_prev(self):
        if self.current_slide > 0:
            self.current_slide -= 1
            self.update_navigation_state()

    def update_navigation_state(self):
        self.content_area.setCurrentIndex(self.current_slide)
        self.btn_prev.setVisible(self.current_slide > 0)

        if self.current_slide == len(self.slides_config) - 1:
            self.btn_next.setText(self.t("btn_close"))
            self.btn_next.setObjectName("NavBtnFinish")
        else:
            self.btn_next.setText(self.t("btn_next"))
            self.btn_next.setObjectName("NavBtnNext")

        self.btn_next.style().unpolish(self.btn_next)
        self.btn_next.style().polish(self.btn_next)

        for i, dot in enumerate(self.dots):
            dot.setProperty("active", "true" if i == self.current_slide else "false")
            dot.style().unpolish(dot)
            dot.style().polish(dot)

    def change_language(self, lang_code):
        if lang_code == self.current_lang: return
        self.current_lang = lang_code
        self.update_ui_texts()

    def update_ui_texts(self):
        self.logo_label.setText(self.t("app_title"))
        for lang, btn in self.lang_buttons.items():
            btn.setProperty("active", "true" if lang == self.current_lang else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if self.current_slide == len(self.slides_config) - 1:
            self.btn_next.setText(self.t("btn_close"))
        else:
            self.btn_next.setText(self.t("btn_next"))
        self.btn_prev.setText(self.t("btn_prev"))

        for data in self.slides_data:
            data["title_widget"].setText(self.t(data["title_key"]))
            data["text_widget"].setHtml(self.t(data["text_key"]))

            for btn_data in data.get("buttons", []):
                btn_data["widget"].setText(self.t(btn_data["key"]))

    def load_stylesheet(self):
        qss_path = os.path.join(self.base_path, "style.qss")
        if not os.path.exists(qss_path):
            return
        with open(qss_path, "r", encoding="utf-8") as f:
            css = f.read()
        # QSS всегда побеждает setFont(), поэтому инжектируем шрифт прямо в CSS
        if self.custom_font_family != "sans-serif":
            f = self.custom_font_family
            css += f'\nQLabel#LogoLabel {{ font-family: "{f}"; font-size: 16px; font-weight: bold; }}'
        self.setStyleSheet(css)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TutorialApp()
    window.showMaximized()
    sys.exit(app.exec())
