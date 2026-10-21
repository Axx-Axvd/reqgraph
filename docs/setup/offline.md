# Офлайн-профиль: Ollama на ноутбуке (Windows, CPU)

Проверено 2026-10-21 по ollama.com/library. Профиль `local` нужен для двух вещей: smoke-прогонов без сети и офлайн-стенда на защите (T-505). Качество маленьких моделей для экспериментов не годится: результаты H1–H4 считаются только на облачной модели (ADR-011).

## Какую модель взять

| Тег | Размер | Контекст | Зачем |
|---|---|---|---|
| `qwen3:1.7b` | 1.4 ГБ | 40K | smoke-тесты роутера и CLI: быстро, JSON обычно валиден |
| `qwen3:4b` | 2.5 ГБ | 256K | **основной `local`**: короткие задачи Analyst и Modeler на демо-брифе |
| `qwen3.5:2b` | 2.7–3.1 ГБ | 256K | запасной вариант; мультимодальная, поэтому тяжелее при той же пользе |

Модели 8B и крупнее (`qwen3:8b` 5.2 ГБ, `gemma4:e4b` 6.6+ ГБ) на CPU слишком медленные для интерактивного демо. Для профиля `local` в `roles.yaml` (T-005): `ollama/qwen3:4b`.

## Установка и проверка

```powershell
winget install --id Ollama.Ollama -e
ollama --version
ollama pull qwen3:1.7b
ollama pull qwen3:4b
ollama list
```

Сервис слушает `http://localhost:11434`, OpenAI-совместимый endpoint — `http://localhost:11434/v1` (`OLLAMA_BASE_URL` в `.env`).

## Замер скорости на CPU

```powershell
ollama run qwen3:4b --verbose "Сформулируй одно функциональное требование к онлайн-записи в автосервис по шаблону EARS."
```

В конце вывода посмотрите `eval rate` — это токены в секунду генерации, и `prompt eval rate` — скорость чтения промпта. Запишите оба числа в `docs/journal.md`.

| eval rate | Вывод |
|---|---|
| ≥ 10 ток/с | `qwen3:4b` подходит для живого офлайн-демо |
| 4–10 ток/с | демо на `qwen3:1.7b` или replay записанных прогонов |
| < 4 ток/с | на защите только replay (T-505); живой прогон — на облачной модели при наличии сети |

Чтобы Ollama не занимала память, когда не нужна: `ollama stop qwen3:4b`. Модель выгружается и сама, через 5 минут простоя.

## Проверка через doctor

```powershell
uv run python scripts/doctor.py      # строка "services ollama OK"
```

Перед защитой пройдите репетицию при выключенном Wi-Fi: `uv run streamlit run apps/demo/app.py` с `REQGRAPH_PROFILE=local` и пустым `DATABASE_URL` (SQLite) — появится в T-505 — и `doctor.py --offline`. Docker не нужен.
