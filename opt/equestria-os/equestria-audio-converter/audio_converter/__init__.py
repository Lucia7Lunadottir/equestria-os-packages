"""Equestria Converter — конвертер аудио и видео (PyQt6 + ffmpeg).

Слои (каждый знает только о слоях выше себя в этом списке):
  _kit, formats, fx, probe      — данные и мелкие функции, без окон
  commands, presets             — сборка команд ffmpeg, готовые наборы
  convert_queue                 — запуск ffmpeg по очереди
  style, widgets                — оформление и общие виджеты
  audio_page, video_page,
  presets_panel, file_list      — отдельные панели окна
  window                        — главное окно, склеивает панели
  app                           — запуск программы
"""
