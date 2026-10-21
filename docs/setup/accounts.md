# Ключи и сервисы: чек-лист автора

Проверено 2026-10-21. Источники: живые ответы API из облачной VM (`GET /api/v1/key` у OpenRouter, заголовки `x-ratelimit-*` у Groq), официальные страницы тарифов Supabase и Streamlit. Лимиты меняются, поэтому перед S6 их нужно перепроверить командой `uv run python scripts/doctor.py --chat`.

Cerebras исключён из проекта (решение автора, см. docs/journal.md).

## Сейчас (S0)

| Сервис | Где взять ключ | Переменная | Бесплатно на 21.10.2026 | Роль |
|---|---|---|---|---|
| OpenRouter | https://openrouter.ai/settings/keys | `OPENROUTER_API_KEY` | модели `:free` и роутер `openrouter/free`; **50 запросов в день** без покупки кредитов (по `/api/v1/key`); порог для повышения дневного лимита — в документации `openrouter.ai/docs/api/reference/limits`; ключу можно задать лимит в $ | основной провайдер, бейзлайны |
| Groq | https://console.groq.com/keys | `GROQ_API_KEY` | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`: **1000 запросов в день, 8000 токенов в минуту** на модель (заголовки ответа). `llama-3.3-70b-versatile` больше недоступна | Interviewer и симулятор в dev |
| Google AI Studio | https://aistudio.google.com/apikey | `GEMINI_API_KEY` | `gemini-3.5-flash-lite` отвечает; `gemini-3.5-flash` и `gemini-flash-latest` 21.10 отдавали 503 (перегрузка); `gemini-2.5-flash` закрыта для новых ключей. Точные RPM и RPD смотрите в AI Studio → **Rate limits** своего проекта: официальная страница из VM недоступна, а сторонние цифры противоречат друг другу | симулятор и судья (другая семья) |

> [!WARNING]
> - **Groq: TPM 8000.** Один вызов Analyst с транскриптом 30–40 ходов (~10–15 тыс. токенов) в лимит не помещается. На Groq — только короткие роли: Interviewer и симулятор.
> - **Google AI Studio.** На бесплатном тарифе запросы могут использоваться для улучшения продуктов Google. Личные данные туда не отправляем.

### Как положить ключи

- **Облачная сессия Claude Code:** network secrets в настройках окружения. Значения в VM нет, прокси подставляет `Authorization` сам. Проверено 21.10: `doctor.py` получает HTTP 200 у всех трёх провайдеров с плейсхолдером вместо ключа.
- **Ноутбук (Windows):** `copy .env.example .env` и вписать ключи. `.env` в git не попадает (см. `.gitignore`).

## Позже (S5, деплой демо — ADR-015)

| Сервис | Где | Что завести | Бесплатно на 21.10.2026 (официальные страницы) |
|---|---|---|---|
| Supabase | https://supabase.com/dashboard | 1 проект `reqgraph-prod` (регион eu-central); нужен только Postgres и строка Supavisor session pooler :5432 | 500 МБ базы на проект, 500 МБ RAM (shared CPU), 5 ГБ egress; **пауза после 1 недели неактивности; максимум 2 активных проекта** |
| Streamlit Community Cloud | https://share.streamlit.io (вход через GitHub) | приложение из `Axx-Axvd/reqgraph`, файл `apps/demo/app.py`; ключи — в Secrets приложения | $0 для публичных репозиториев; ресурсы по docs (данные 2024 года): до ~2.7 ГБ RAM, сон после 12 ч без трафика — перепроверить в T-504 (docs.streamlit.io из облачной VM закрыт) |

## Не нужно

- **Платные кредиты OpenRouter** — только в январе–феврале под эксперименты, по решению автора (бюджет ≤ $20 в месяц). Из РФ оплата картой невозможна; см. 07_deploy.
- **Kroki** — ключ не нужен; `https://kroki.io` доступен из VM (doctor: OK).
