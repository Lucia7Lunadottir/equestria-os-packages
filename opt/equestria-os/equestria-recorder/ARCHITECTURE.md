# Equestria Recorder

`equestria_recorder.py` — только точка входа. Реализация — в `equestria_recorder_app/`,
одна обязанность на файл:

| Файл | Что делает |
|---|---|
| `capture.py` | `MicrophoneCapture` — открывает микрофон, читает отсчёты, применяет усиление, шлёт `chunk` |
| `samples.py` | декодеры форматов микрофона (`Int16Decoder`, `FloatDecoder`); новый формат — новый класс в `_DECODERS` |
| `recording.py` | `RecordingSession` — файл WAV: запись → пауза → продолжение → стоп |
| `playback.py` | `Playback` — прослушивание, в том числе с середины файла (для обрезки) |
| `wav_clip.py` | `WavClip` — 16-битный WAV в памяти: волна, вырезка, запись; имена копий |
| `levels.py`, `formatting.py` | пик и децибелы; время текстом |
| `widgets.py` | карточка, подтверждение, `LevelMeter`, `Waveform` |
| `trim_dialog.py` | окно обрезки (`WavClip` + `Playback`) |
| `window.py` | `MainWindow` — собирает интерфейс и связывает объекты выше |
| `app.py` | запуск Qt |
| `style.py`, `settings.py`, `paths.py`, `localization.py` | тема, файл настроек, пути, каталог переводов |
| `compat.py` | прежние имена модуля `equestria_recorder` для внешних потребителей |

Каждый файл `locales/<код>.json` — отдельный язык, название — `_language_name`.

Пакет ставит модули в `/usr/lib/equestria-recorder`, переводы — в
`/usr/share/equestria-recorder/locales`. Из исходников используется соседний `equestria-qt-kit`.
