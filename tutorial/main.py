import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QStackedWidget, QTextBrowser, QLabel)
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtCore import Qt

class TutorialApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Equestria OS — Путеводитель")
        self.resize(900, 600)
        self.base_path = os.path.dirname(os.path.abspath(__file__))

        # Загрузка фирменного шрифта (только для заголовков!)
        self.custom_font_family = "sans-serif"
        font_path = os.path.join(self.base_path, "equestria_cyrillic.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.custom_font_family = families[0]

        self.init_ui()
        self.load_stylesheet()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Боковая панель
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(250)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(15, 20, 15, 20)
        self.sidebar_layout.setSpacing(10)

        # Заголовок боковой панели (Применяем кастомный шрифт)
        self.lbl_title = QLabel("Equestria OS")
        self.lbl_title.setObjectName("SidebarTitle")
        self.lbl_title.setFont(QFont(self.custom_font_family, 22, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_layout.addWidget(self.lbl_title)
        self.sidebar_layout.addSpacing(20)

        # Основная область контента
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("ContentArea")

        self.nav_buttons = []
        self.add_section("Добро пожаловать", self.get_intro_html())
        self.add_section("Внешний вид", self.get_visuals_html())
        self.add_section("Программы и Обновления", self.get_software_html())
        self.add_section("Игры и Файлы", self.get_games_html())
        self.add_section("Система и Настройки", self.get_system_html())

        self.sidebar_layout.addStretch()

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_area)

        if self.nav_buttons:
            self.switch_page(0)

    def add_section(self, title, html_content):
        btn = QPushButton(title)
        btn.setObjectName("NavBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        index = self.content_area.count()
        btn.clicked.connect(lambda checked, idx=index: self.switch_page(idx))

        self.nav_buttons.append(btn)
        self.sidebar_layout.addWidget(btn)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(30, 30, 30, 30)

        browser = QTextBrowser()
        browser.setObjectName("TextContent")
        browser.setOpenExternalLinks(True)
        browser.setHtml(html_content)
        page_layout.addWidget(browser)

        self.content_area.addWidget(page)

    def switch_page(self, index):
        self.content_area.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setProperty("active", "true")
            else:
                btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def load_stylesheet(self):
        qss_path = os.path.join(self.base_path, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                # Читаем QSS и гарантируем, что кастомный шрифт подхватится для Title
                qss = f.read().replace('"Equestria_Cyrillic"', f'"{self.custom_font_family}"')
                self.setStyleSheet(qss)

    # --- HTML Контент ---
    # Обрати внимание: кастомный шрифт (self.custom_font_family) применяется ТОЛЬКО к <h1> и <h2>.
    # Остальной текст (<p>, <ul>) будет использовать дефолтный sans-serif.

    def get_intro_html(self):
        return f"""
        <h1 style="color: #f5c2e7; font-family: '{self.custom_font_family}', sans-serif; font-size: 32px; font-weight: normal;">Добро пожаловать в Equestria OS! 🐴✨</h1>
        <p style="font-size: 15px; line-height: 1.6;">Добро пожаловать в вашу новую операционную систему! Equestria OS создана на базе мощного Arch Linux, но вам не нужно быть хакером или часами сидеть в терминале, чтобы ей пользоваться.</p>
        <p style="font-size: 15px; line-height: 1.6;">Мы верим, что магия технологий заключается в их простоте. Этот краткий путеводитель поможет вам освоиться, особенно если вы всю жизнь пользовались только Windows.</p>
        <p style="font-size: 15px; line-height: 1.6;">Используйте меню слева, чтобы узнать, как работают основные компоненты системы.</p>
        """

    def get_visuals_html(self):
        return f"""
        <h2 style="color: #cba6f7; font-family: '{self.custom_font_family}', sans-serif; font-size: 28px; font-weight: normal;">Глава 1. Настройте систему под себя</h2>
        <p style="font-size: 15px; line-height: 1.6;">Рабочий стол — это ваш холст. Equestria OS позволяет менять интерфейс в пару кликов без необходимости копаться в сложных настройках KDE.</p>
        <ul style="font-size: 15px; line-height: 1.8;">
            <li><b>Welcome Hub (Центр приветствия):</b> Ваша стартовая точка. Отсюда можно быстро перейти к настройкам и выбрать программы для автозапуска.</li>
            <li><b>Character Theme Changer:</b> Забудьте про скучные серые окна. Выберите цветовую схему, вдохновленную любимыми персонажами.</li>
            <li><b>Task Panel Changer:</b> Привыкли к панели внизу, как в Windows? Или хотите док по центру? Эта утилита мгновенно переключает макеты панелей задач под ваш вкус.</li>
        </ul>
        """

    def get_software_html(self):
        return f"""
        <h2 style="color: #a6e3a1; font-family: '{self.custom_font_family}', sans-serif; font-size: 28px; font-weight: normal;">Глава 2. Программы и Обновления</h2>
        <p style="font-size: 15px; line-height: 1.6;">В Linux программы устанавливаются не через поиск файлов в браузере, а через удобные магазины и менеджеры пакетов:</p>
        <ul style="font-size: 15px; line-height: 1.8;">
            <li><b>Essentials (Базовые программы):</b> Здесь собраны самые нужные программы на каждый день. <b>Здесь же обновляется система!</b> Просто нажмите кнопку обновления, и Equestria OS сама скачает свежие версии всех пакетов.</li>
            <li><b>App Store:</b> Наш официальный магазин для поиска и установки новых программ из репозиториев pacman и AUR.</li>
            <li><b>Package Manager:</b> Если нужно почистить систему от лишнего, зайдите сюда. Утилита покажет установленный софт и позволит безопасно его удалить.</li>
        </ul>
        <p style="font-size: 14px; color: #a6adc8;"><i>Примечание: Если вам нужны приложения в формате Flatpak, вы можете использовать предустановленный магазин KDE Discover.</i></p>
        """

    def get_games_html(self):
        return f"""
        <h2 style="color: #fab387; font-family: '{self.custom_font_family}', sans-serif; font-size: 28px; font-weight: normal;">Глава 3. Windows-игры и Файлы</h2>
        <p style="font-size: 15px; line-height: 1.6;">Переход на новую систему пугает тем, что «старые программы не заработают». Мы постарались смягчить этот переход.</p>
        <ul style="font-size: 15px; line-height: 1.8;">
            <li><b>Запуск .exe файлов (Proton Starter):</b> Осталась любимая игра для Windows? Просто дважды кликните по <code>.exe</code> файлу! Система сама перехватит его и запустит через слой совместимости Proton. Никаких сложных настроек терминала!</li>
            <li><b>Умный перенос файлов (Relocator):</b> Если у вас мало места на SSD и вы хотите перенести тяжелую игру на HDD, используйте эту утилиту. Она перенесет папку и оставит на старом месте "ссылку". Лаунчеры (например, Steam) даже не заметят, что файлы переехали!</li>
        </ul>
        """

    def get_system_html(self):
        return f"""
        <h2 style="color: #89b4fa; font-family: '{self.custom_font_family}', sans-serif; font-size: 28px; font-weight: normal;">Глава 4. Система и Настройки</h2>
        <p style="font-size: 15px; line-height: 1.6;">Даже глубокие системные настройки у нас имеют понятный графический интерфейс:</p>
        <ul style="font-size: 15px; line-height: 1.8;">
            <li><b>Services Manager:</b> Управление фоновыми службами (например, Bluetooth или печать). Включайте и выключайте их одним кликом.</li>
            <li><b>Swap Manager:</b> Управление файлом подкачки. Если вам не хватает оперативной памяти (RAM), здесь можно легко создать файл подкачки или настроить его размер.</li>
            <li><b>Rank Mirrors:</b> Если программы скачиваются слишком медленно, эта утилита найдет самые быстрые серверы в вашей или соседних странах для ускорения загрузок.</li>
        </ul>
        """

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TutorialApp()
    window.show()
    sys.exit(app.exec())
