# Дневник разработки reqgraph

Формат записи: дата · задача · решения · проблемы · что дальше. Записи идут в главу диплома «Реализация», поэтому фиксируем и неудачи.

---

## 2026-10-21 · Этап 0 (preflight)

**Решения**

- **Python 3.12.** `uv python install 3.12` в облачной VM скачал CPython 3.12.13 за 3 с. Фиксируем `.python-version = 3.12` и `requires-python = ">=3.12,<3.13"` в T-001. На ноутбуке автора тоже 3.12. Матрица 3.12 + 3.13 в CI не нужна. Системный Python в VM (3.13) не используем.
- **Supabase CLI в VM.** `pnpm dlx supabase --version` → 2.121.0, бинарник скачивается. Но образы локального стека (`supabase start`) по умолчанию тянутся с `public.ecr.aws`, а слои отдаёт CloudFront, который прокси VM блокирует (403). Docker Hub отвечает 429 — это анонимный лимит на общий IP. **Допущение:** проверка миграций T-004 (`supabase db reset`) идёт в GitHub Actions (`supabase/setup-cli`) и на ноутбуке автора. В VM доступны только `supabase --version` и `supabase migration new`.
- **Docker в VM** не запускается сам: демон стартует вручную (`dockerd &`). `hello-world` работает через `mirror.gcr.io/library/hello-world`.
- **Защита ветки main** откладывается до T-003: нужен хотя бы один зелёный прогон `ci.yml`. **Задача на потом:** в T-003 включить правило для main — PR обязателен, статус-чек `ci` обязателен, запрет force-push.
- **DoD** отмечается только в `docs/backlog.md`. В `08_plan.md` и `10_claude.md` теперь стоит ссылка туда.
- **Cerebras исключён из проекта** (решение автора: платный). Убран из `.env.example`, 02_arch, 06_models, 07_deploy и docs/prompts/preflight.md. Симулятор заказчика «другой семьи» теперь Groq (Llama 3.3 70B) или Gemini Flash (AI Studio). `docs/tech-design.pdf` пока со старым текстом, Markdown-версия главнее.
- **Постоянные инструкции сессий** лежат в `docs/prompts/` (preflight, task, review, debug).

**Проблемы**

- Сеть облачного окружения не пускает `openrouter.ai`, `api.groq.com`, `kroki.io`, `supabase.com`, `ollama.com` и сайты документации (403 на CONNECT). Network secrets провайдеров проверить нельзя, пока автор не добавит хосты в Allowed domains.
