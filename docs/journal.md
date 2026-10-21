# Дневник разработки reqgraph

Формат записи: дата · задача · решения · проблемы · что дальше. Записи идут в главу диплома «Реализация», поэтому фиксируем и неудачи.

---

## 2026-10-21 · Этап 0 (preflight)

**Решения**

- **Python 3.12.** `uv python install 3.12` в облачной VM скачал CPython 3.12.13 за 3 с. Фиксируем `.python-version = 3.12` и `requires-python = ">=3.12,<3.13"` в T-001. На ноутбуке автора тоже 3.12. Матрица 3.12 + 3.13 в CI не нужна. Системный Python в VM (3.13) не используем.
- **Supabase CLI в VM.** `pnpm dlx supabase --version` → 2.121.0, бинарник скачивается. Сначала образы с `public.ecr.aws` и Docker Hub не качались (403 и 429), после того как автор открыл хосты — качаются. **Допущение:** миграции (теперь T-503, хранилище демо) применяет GitHub Actions (`supabase/setup-cli`, `supabase db push`); локальный стек Supabase не нужен (ADR-015).
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
