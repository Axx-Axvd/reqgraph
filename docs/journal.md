# Дневник разработки reqgraph

Формат записи: дата · задача · решения · проблемы · что дальше. Записи идут в главу диплома «Реализация», поэтому фиксируем и неудачи.

---

## 2026-10-21 · Этап 0 (preflight)

**Решения**

- **Python 3.12.** `uv python install 3.12` в облачной VM скачал CPython 3.12.13 за 3 с. Фиксируем `.python-version = 3.12` и `requires-python = ">=3.12,<3.13"` в T-001. На ноутбуке автора тоже 3.12. Матрица 3.12 + 3.13 в CI не нужна. Системный Python в VM (3.13) не используем.
- **Supabase CLI в VM.** `pnpm dlx supabase --version` → 2.121.0, бинарник скачивается. Сначала образы с `public.ecr.aws` и Docker Hub не качались (403 и 429), после того как автор открыл хосты — качаются. Миграции — T-004: `supabase db reset` в GitHub Actions и на ноутбуке автора, `supabase db push` в staging и prod (migrate.yml, T-506). *(Исправлено 22.10: в первой редакции здесь было допущение из отменённого ADR-015.)*
- **Docker в VM** не запускается сам: демон стартует вручную (`dockerd &`). `hello-world` работает через `mirror.gcr.io/library/hello-world`.
- **Защита ветки main** откладывается до T-003: нужен хотя бы один зелёный прогон `ci.yml`. **Задача на потом:** в T-003 включить правило для main — PR обязателен, статус-чек `ci` обязателен, запрет force-push.
- **DoD** отмечается только в `docs/backlog.md`. В `08_plan.md` и `10_claude.md` теперь стоит ссылка туда.
- **Cerebras исключён из проекта** (решение автора: платный). Убран из `.env.example`, 02_arch, 06_models, 07_deploy и docs/prompts/preflight.md. Симулятор заказчика «другой семьи» — Gemini Flash-Lite (AI Studio); Llama 3.3 70B на Groq больше нет (см. ниже). `docs/tech-design.pdf` пока со старым текстом, Markdown-версия главнее.
- **Постоянные инструкции сессий** лежат в `docs/prompts/` (preflight, task, review, debug).
- **Network secrets проверены.** Запросы через openai SDK 3.36.0 к OpenRouter, Groq и Google AI Studio (OpenAI-совместимый endpoint) проходят с `api_key="placeholder"`: прокси подставляет ключ сам. `scripts/doctor.py --chat` получает HTTP 200 у всех трёх.
- **Модели из 06_models устарели.** Нет `gpt-oss-120b:free` на OpenRouter, `llama-3.3-70b-versatile` на Groq, `gemini-2.5-flash` для новых ключей. Живые списки — в docs/research/2026-10-models.md.

**Проблемы**

- (решено в тот же день: автор открыл хосты) Сеть облачного окружения не пускала `openrouter.ai`, `api.groq.com`, `kroki.io`, `supabase.com`, `ollama.com` и сайты документации (403 на CONNECT).

## 2026-10-21 · Этап 0 (продолжение): готовые средства вместо своего кода

**Запрос автора:** везде, где можно, взять сторонние API, библиотеки и сервисы, чтобы писать меньше кода и тратить меньше токенов.

**Проверено вживую** (venv на Python 3.12.13, ключи автора через network secrets):
- pydantic-ai-slim 2.59 — structured output, ретраи, FallbackModel, цена (genai-prices); Groq, Gemini, OpenRouter — OK;
- Kroki — скомпилированы все модели garage61, включая Structurizr (закрыт открытый пункт REVIEW.md);
- pandoc (pypandoc-binary 1.17) делает DOCX;
- Streamlit +36 МБ, Gradio +159 МБ;
- HF Spaces для Gradio и Docker требуют PRO;
- bpmn-auto-layout — только Node и только первый участник.

**Решения автора:**
- демо — одно Streamlit-приложение (ADR-015);
- SND-002 — pm4py с переводчиком событийного шлюза (ADR-014);
- до января — только бесплатные модели.

**Решения по «готовое вместо своего»** (по общему запросу автора):
- LLM-слой на pydantic-ai (ADR-013);
- DOCX через pandoc (ADR-016);
- evals на pydantic-evals;
- статистика на scipy и statsmodels.

**Что изменилось в плане:**
- S0 без базы: T-004 упразднена, миграции — в T-503;
- S5: 7 задач → 5 (T-501…T-505), без TypeScript, FastAPI, очереди, Vercel и Render;
- ноутбуку не нужны Docker, WSL2, Node и Supabase CLI;
- оценка трудоёмкости: ~190–260 ч → ~170–240 ч.

**Методические правки при переписывании** (вынесены в отчёт этапа 0 на подтверждение):
- матрица экспериментов — 12 test-сценариев × 3 персоны × 8 методов, вместо «15 × 3 × 6 = 270»;
- согласие трёх экспертов — каппа Флейса вместо каппы Коэна (она для двух оценщиков);
- Analyst получил право создавать ACT (раньше 03_agents и 04_data противоречили друг другу);
- в префиксы 04_data добавлен C4-EXT-01.

**Проблемы:**
- docs.streamlit.io и huggingface.co закрыты прокси облачной VM, поэтому лимиты Streamlit Cloud взяты из поиска (данные 2024 года) — перепроверить в T-504.
- `docs/tech-design.pdf` не пересобран и отстаёт от Markdown.

**Итог этапа 0:** [docs/preflight-report.md](preflight-report.md). Задачи в GitHub: 41 issue, 8 вех, 23 метки. Дальше — T-001 (монорепо на uv) по команде автора.

## 2026-10-21 · Откат ADR-015: веб-стек возвращён

**Решение автора:** вернуть веб-часть как было до этапа 0 — Next.js на Vercel, FastAPI и воркер на Render Free, Supabase (Postgres, Auth, Storage, Realtime). ADR-015 (одно приложение на Streamlit) помечен «отклонено»; ADR-001, 007, 008, 009 снова «принято» без уточнений.

**Что вернулось:**
- T-004 — миграции Supabase в S0;
- E5 из 7 задач (T-501…T-507) в исходной редакции;
- `07_deploy`, схема Supabase в `04_data`, стек и дерево `apps/api` + `apps/web` в `02_arch`;
- `.env.example` с переменными Supabase и `NEXT_PUBLIC_API_URL`;
- команды pnpm, supabase и docker compose в CLAUDE.md;
- npm в Dependabot, ESLint и Prettier в VS Code;
- в `doctor.py` снова проверяются Node, pnpm, Docker и Supabase CLI;
- в чек-листе Windows снова Node, Docker Desktop и Supabase CLI;
- оценка трудоёмкости ~185–255 ч.

**Что осталось из этапа 0:**
- pydantic-ai (ADR-013), pm4py с переводчиком (ADR-014), pandoc (ADR-016);
- pydantic-evals, scipy и statsmodels;
- новые модели и лимиты, исключение Cerebras;
- методические правки (матрица, каппа Флейса, ACT, C4-EXT-01).

**Риск, который снова актуален:** Render Free 512 МБ против 132–250 МБ импортов. Меры: ленивые импорты (pm4py — только в SND-002), замер в T-506, запасной вариант — Railway или Fly (~$5).

**GitHub после отката:** созданы `area:api`, `area:web` и задачи T-004 (#43), T-506 (#44), T-507 (#45); обновлены T-001, T-003, T-501…T-505, T-605, T-701 и описания вех M0, M5; метка `area:demo` удалена. Итого 44 задачи, 8 вех, 24 метки; сверка backlog ↔ GitHub ↔ 08_plan — без расхождений.

## 2026-10-22 · T-001: каркас монорепо

**Решения**

- **uv workspace:** корень — виртуальный (`package = false`), участники `packages/core` (пакет `reqgraph`) и `apps/api` (заглушка `reqgraph-api` без зависимостей до T-501). Сборка — `uv_build`. Единственная runtime-зависимость ядра — typer 0.27.3 (CLI). `reqgraph --version` читает версию через `importlib.metadata`.
- **Проверки:** ruff (line-length 100, как в `.editorconfig`), mypy strict, pytest с `--strict-markers --disable-socket`, pytest-cov только отчётом. Правила RUF001–RUF003 выключены: сообщения проверок и промпты по соглашению на русском, кириллица — не «двусмысленные символы».
- **ruff 0.17 форматирует Python-блоки внутри Markdown.** Первый `ruff format .` переписал примеры кода в `docs/tech-design/03_agents.md` и `05_ci.md`. Откатил, `docs/**` исключён из форматирования: примеры — часть проекта, а не код.
- **Существующие скрипты** (`doctor.py`, `github_bootstrap.py`) отформатированы ruff, поведение не менялось.
- **Next.js 16.4.2** через `create-next-app` (App Router, `src/`, TypeScript strict, ESLint flat config, без Tailwind и UI-библиотек). Шаблонная страница заменена заглушкой.
- **TypeScript 7.0.2 и ESLint 10 не подошли:** typescript-eslint 8.72 требует TypeScript < 6.1, плагины eslint-config-next 16.4.2 (react, jsx-a11y, import) — ESLint ≤ 9. Закреплены TypeScript 6.0.3 и ESLint 9.39.5; пересмотреть, когда плагины обновятся (Dependabot).
- **`next/font/google` убран:** он скачивает шрифты при сборке, а офлайн-стенд должен собираться без сети. Системные шрифты.
- **pre-commit:** базовые хуки pre-commit-hooks v6.0.0; ruff и mypy — локальные хуки через `uv run`, чтобы версии совпадали с `uv.lock` и CI.
- **Решение по пункту 16 отчёта preflight (принято автором 21.10):** связь «требование → элемент модели» хранит `realized_by` в требованиях; `realizes` в DSL — зеркало; расхождение — error TRC-004. Реализация — T-101 (граф и патчи) и T-107 (проверки трассировки).

**Проблемы**

- В VM демон Docker не запущен, поэтому `doctor.py --offline` показывает FAIL для docker daemon; к T-001 не относится (нужен с T-004).

**Что дальше:** T-003 — ci.yml (ubuntu + windows) и защита main.

## 2026-10-22 · T-003: CI

**Решения автора:** DoD S6 «расход ≤ $25» остаётся (два месяца экспериментов при потолке $20 в месяц); T-001 смержен (PR #47).

**Решения**

- `ci.yml`: на push в main и на каждый PR. Задачи `python` и `web` идут на ubuntu и windows (`fail-fast: false`), итоговая задача `ci` собирает их результат — под защиту main ставится одна проверка с именем `ci`, даже если матрица изменится.
- На push работает только main: в ветках CI запускается через PR, иначе каждый коммит гонялся бы дважды.
- `pre-commit` — только на ubuntu (хуки не зависят от ОС). `supabase db reset` добавляется в T-004.
- Действия: checkout v7, setup-uv v7, pnpm/action-setup v6 (версия pnpm — из `packageManager`), setup-node v7; Dependabot обновляет их (github-actions в `.github/dependabot.yml`).
- Правило для main (PR и проверка `ci` обязательны, запрет force-push) меняет настройки GitHub вне репозитория: по правилам этапа 0 сначала показываю, что именно включаю, и жду «ок».

## 2026-10-23 · T-002: документы проекта; защита main

**Защита main (хвост T-003).** Автор дал «ок». Правило `protect-main` (ruleset: только PR, обязательная проверка `ci` с актуальной веткой, запрет force-push и удаления) через API включить не удалось: прокси облачной сессии отвечает 403 «Write access to this GitHub API path is not permitted through this proxy». Обходить не стал — автор включает правило в Settings → Rules → Rulesets.

**Сверка T-002**

- LICENSE (MIT, 2026), README с разделом «Лицензии зависимостей», ADR 001–016 — на месте; относительные ссылки во всех Markdown целы, все T-xxx есть в бэклоге.
- ADR 001–012 и 013–016 разложены по разделам по-разному; обе раскладки — облегчённый MADR. Тексты принятых ADR не переписывал (так требует README ADR), добавил `docs/adr/template.md` для новых решений.
- В CLAUDE.md часть команд ещё не существует (`reqgraph check`, `reqgraph schemas`, `supabase`, `docker compose`). Разделил список на «работают сейчас» и «появятся с задачами», чтобы сессии не запускали несуществующее.
- README: бейдж CI; текущие лицензии (typer, Next.js, React — MIT).

**Решение автора:** DoD S6 «расход ≤ $25» оставлен.

**Что дальше:** T-004 — миграции Supabase (схема 04_data, RLS, seed) и `supabase db reset` в CI.
