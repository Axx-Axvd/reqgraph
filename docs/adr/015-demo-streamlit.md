# ADR-015: Демо — одно Streamlit-приложение, Supabase только как Postgres

- Статус: **отклонено** (2026-10-21, решение автора: вернуть Next.js + FastAPI + воркер + Vercel + Render, ADR-008 и ADR-009 остаются в силе)
- Дата: 2026-10-21
- Предлагалось заменить: [ADR-008](008-deploy.md) (Vercel + Render), [ADR-009](009-pg-queue.md) (очередь в Postgres); сузить [ADR-007](007-supabase.md) и [ADR-001](001-monorepo.md)

> **Почему отклонено.** Решение было принято на этапе 0 и в тот же день отменено автором: для портфолио и зарубежных программ важнее полноценный веб-стек (Next.js, FastAPI, Supabase Auth и Realtime), чем экономия кода в S5. Действуют ADR-001, 007, 008, 009 в исходной редакции. Риск по памяти Render Free (512 МБ) остаётся и закрывается мерами из 07_deploy: ленивые импорты, замер в T-506, запасной вариант — Railway или Fly. Текст ниже сохранён как запись рассмотренной альтернативы.

## Контекст

План S5 состоял из 7 задач на двух языках:
- Next.js на Vercel;
- FastAPI и воркер с очередью на Render Free (512 МБ, засыпает через 15 минут);
- Supabase Auth, Storage, Realtime и RLS-политики;
- генерация TS-типов из OpenAPI.

Замеры 21.10.2026: импорты runtime занимают 132–250 МБ ещё до первого запроса, так что 512 МБ — на грани. Цель демо — показать конвейер комиссии и зарубежным программам, а не построить SaaS.

## Решение

- `apps/demo/app.py` — одно приложение на Streamlit (Apache-2.0, импорт +36 МБ):
  - интервью-чат: `st.chat_input`; пауза и продолжение — LangGraph `interrupt` / `Command(resume=…)` с чекпоинтером;
  - граф трассировки: `st.graphviz_chart`;
  - BPMN: bpmn-js с CDN внутри `components.html`, водяной знак bpmn.io не скрываем;
  - отчёт CI: таблица с фильтром; выбор ошибки подсвечивает узлы графа;
  - выгрузка SRS, ТЗ и ReqIF: `st.download_button`.
- Хостинг — Streamlit Community Cloud ($0, публичный репозиторий; ресурсы по docs на 2024 год — до ~2.7 ГБ RAM, сон после 12 ч без трафика; перепроверить в T-504).
- Хранилище:
  - в облаке — Supabase Postgres (session pooler :5432): PostgresSaver в схеме `lg` и таблицы projects, graph_revisions, runs, run_events;
  - локально и офлайн — SQLite (`langgraph-checkpoint-sqlite`) и FileStore.
- Входа нет. Лимиты демо: прогоны на сессию, общий дневной потолок $, свой ключ OpenRouter (BYOK) в памяти сессии.
- RLS включён на всех таблицах без политик для `anon`: доступ только с сервера.
- Офлайн-стенд для защиты: `uv run streamlit run apps/demo/app.py` + Ollama + SQLite; Docker не нужен.

## Последствия

- E5 (веб и деплой): 7 задач → 5. Нет TypeScript, pnpm, FastAPI, очереди, JWT/JWKS, Realtime, второго деплоя.
- На ноутбуке автора не нужны Docker Desktop, WSL2 и Supabase CLI. Миграции применяет CI (`supabase db push`).
- S0 больше не содержит базу: миграции переезжают в S5.
- Минусы:
  - фронтенд проще, чем на Next.js, — для CV это «AI-демо», а не «full-stack»;
  - нет кликабельного графа React Flow;
  - Streamlit перезапускает скрипт при каждом действии, поэтому состояние держим в `st.session_state` и чекпоинтере;
  - доступность `*.streamlit.app` из РФ не проверена — защита всё равно идёт на офлайн-стенде.

## Альтернативы

- Next.js + FastAPI + Vercel + Render (ADR-008/009) — больше кода и риск по памяти.
- Gradio на Hugging Face Spaces — с 2026 года Gradio-Spaces на бесплатном железе требуют PRO.
- Gradio на Render — импорт Gradio +159 МБ, снова упираемся в 512 МБ.
