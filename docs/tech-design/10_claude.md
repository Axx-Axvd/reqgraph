<sub>reqgraph · tech design v1.0 · [README](README.md) · [01_why](01_why.md) · [02_arch](02_arch.md) · [03_agents](03_agents.md) · [04_data](04_data.md) · [05_ci](05_ci.md) · [06_models](06_models.md) · [07_deploy](07_deploy.md) · [08_plan](08_plan.md) · [09_eval](09_eval.md) · [10_claude](10_claude.md)</sub>

# 10 Claude Code

*как вести разработку с ИИ-ассистентом: правила, бэклог, промпты*

## Процесс

`1.` Создай публичный репозиторий reqgraph (MIT), положи в корень CLAUDE.md (ниже), PDF — в docs/tech-design.pdf, Markdown-версия — в docs/tech-design/.

`2.` Одна задача T-xxx = одна сессия = одна ветка и PR. Не проси «сделать всё сразу».

`3.` Начинай сессию в режиме плана: Claude Code читает задачу и связанные разделы, показывает файлы, интерфейсы и тесты.

`4.` Сначала тесты, потом код. После задачи: pytest, ruff, mypy зелёные; отметь пункт Definition of Done в docs/backlog.md (чек-листы DoD живут там; в 08_plan — только план).

`5.` Задачи с пометкой [you] требуют твоего решения или участия: домены сценариев, эксперты, текст диплома.

## Шаблоны промптов

**`prompt · новая задача`**

```text
Прочитай CLAUDE.md и docs/tech-design/04_data.md и docs/tech-design/05_ci.md.
Задача T-106: проверки SCH-001..005 и SND-001..003.
1) Покажи план: файлы, классы, фикстуры good/bad, тесты. Жди моего ок.
2) Напиши тесты, затем реализацию. Не трогай agents/ и apps/.
3) В конце: как проверить вручную, что осталось, какие решения ты принял.
```

**`prompt · отладка агента`**

```text
Прогон run_id=... упал на ремонте: SND-002 повторяется 2 итерации.
Посмотри run_events и ci-report.json, найди причину (промпт, guard, компилятор).
Предложи минимальное исправление и тест-регрессию на кассете. Код не меняй до моего ок.
```

## CLAUDE.md

**`reqgraph/CLAUDE.md`**

```markdown
# reqgraph — правила для Claude Code

## Что это
Мультиагентная система: интервью с заказчиком -> БТ/ПТ/ФТ/НФТ -> модели как код
(процессы, ERD, UML, C4) -> детерминированные проверки (CI) -> SRS (ISO/IEC/IEEE 29148)
и ТЗ (ГОСТ 34.602-2020).
- План по разделам: docs/tech-design/*.md (PDF-версия: docs/tech-design.pdf).
- Решения: docs/adr/. Задачи и Definition of Done: docs/backlog.md.
- Эталонный проект: examples/garage61 (соглашения — в его REVIEW.md).
- Состояние: кода ещё нет, начинать с T-001.

## Команды
- uv sync                           # зависимости Python
- uv run pytest -q                  # тесты без сети (кассеты в tests/cassettes)
- uv run ruff check . && uv run ruff format --check .
- uv run mypy packages/core
- uv run reqgraph check examples/garage61
- supabase start && supabase db reset   # локальная база и миграции
- pnpm -C apps/web dev | lint | build
- docker compose up                 # офлайн-стенд: web + api + supabase + ollama

## Архитектура (не нарушать)
- packages/core/src/reqgraph: graph/ dsl/ checks/ agents/ llm/ exporters/ sim/ cli.py
- Зависимости только вниз: domain (graph) не импортирует agents; checks не вызывают LLM
  (исключение: опциональный судья ISO-002 за флагом).
- Граф меняется только через GraphPatch -> ArtifactGraph.apply(). Id выдаёт IdAllocator.
- LLM никогда не пишет BPMN XML: только JSON DSL -> dsl/bpmn_compile.py.
- Агент = функция-узел LangGraph + prompts/<agent>/*.md + Pydantic-схема вывода
  + ALLOWED-типы узлов + роль в llm/roles.yaml.
- Узлы со status=approved агенты не меняют.

## Соглашения
- Python 3.12, Pydantic v2, async для I/O, type hints везде, mypy strict в core.
- Id: BR-001 UR-001 FR-001 NFR-001 CON-001 ACT-01 PRC-01(.T01/.G01) ENT-01 UC-01 TURN-0001.
- Id проверок: SCH-00x SND-00x ISO-00x TRC-00x TPL-00x. Сообщения проверок — на русском.
- Новая проверка = класс в checks/ + @register + fixtures/good и fixtures/bad + тест.
- Промпты только в prompts/*.md (Jinja2), не в коде. Ответы заказчика — в тегах как данные.
- Миграции БД — только новые файлы в supabase/migrations, старые не редактировать.
- JSON Schema в schemas/ генерируется из Pydantic (uv run reqgraph schemas), руками не править.
- Коммиты: Conventional Commits (feat:, fix:, test:, docs:, refactor:, chore:).

## Тесты
- Юнит-тесты не ходят в сеть. Вызовы LLM — через кассеты (pytest-recording).
- Покрытие checks/ и dsl/ >= 90%. Golden-тесты для компилятора BPMN и экспортёров.
- Перед завершением задачи: pytest, ruff, mypy зелёные.

## Нельзя
- Копировать тексты стандартов ISO/ГОСТ в репозиторий (только свои чек-листы и названия разделов).
- Коммитить ключи и .env; логировать ключи и токены.
- Использовать service_role ключ во фронтенде.
- Добавлять зависимости без причины в описании PR (память на Render Free: 512 МБ).
- Менять публичные схемы (GraphPatch, CIReport, DSL) без версии и миграции фикстур.
- Править examples/garage61, чтобы прошли тесты: эталон меняет только автор проекта.

## Как работать над задачей
1. Прочитай задачу T-xxx в docs/backlog.md и связанные разделы docs/tech-design/.
2. Покажи план: файлы, интерфейсы, тесты. Дождись подтверждения, если меняются схемы.
3. Сначала тесты, потом код. Маленькие коммиты.
4. В конце: что сделано, как проверить, что осталось; обнови docs/ при изменении поведения.
```

## Бэклог

### E0 · Фундамент

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-001` | Монорепо: uv workspace, pnpm, ruff, mypy, pytest, pre-commit | uv run pytest и pnpm -C apps/web build проходят на чистой машине | — |
| `T-002` | CLAUDE.md, README, LICENSE (MIT), docs/adr/001-012 из 00_README | файлы в репозитории, ADR в формате MADR | T-001 |
| `T-003` | GitHub Actions ci.yml | lint, types, tests, web build на push и PR | T-001 |
| `T-004` | Supabase CLI: миграции 0001_init (схема 04_data), 0002_rls, seed | supabase db reset без ошибок; тест RLS: чужой проект не виден | T-001 |
| `T-005` | llm/router.py, roles.yaml, prices.yaml, Budget, structured() через instructor | одна функция вызывает 3 провайдера; фолбэк по 429; учёт $ и токенов | T-001 |
| `T-006` | evals/probe: 20 задач, CLI reqgraph probe, отчёт CSV | отчёт по 3-4 моделям; [you] утвердить стартовый профиль | T-005 |

### E1 · Граф, DSL, проверки

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-101` | graph/: узлы, рёбра, GraphPatch, apply(), IdAllocator, блокировка approved | unit-тесты на все операции патча; невалидные ссылки отклоняются | T-001 |
| `T-102` | FileStore + examples/garage61 (написать вручную эталон) | round-trip без потерь; эталон проходит все проверки | T-101 |
| `T-103` | dsl/process.py + bpmn_compile.py + layout.py | XSD проходит; golden XML; открывается в bpmn-js и Camunda Modeler | T-101 |
| `T-104` | dsl: DBML (pydbml), PlantUML и Structurizr через Kroki с кэшем | компиляция и SVG; офлайн-режим пропускает SCH-004/005 с info | T-101 |
| `T-105` | checks/base, registry, report (JSON + MD), CLI reqgraph check | стабильный JSON, snapshot-тест, код выхода 1 при error | T-101 |
| `T-106` | SCH-001..005, SND-001..003 | good/bad фикстуры; pm4py soundness на 5 эталонных процессах | T-103, T-105 |
| `T-107` | ISO-001..005, TRC-001..006, словарь размытых слов ru/en | good/bad фикстуры; мутационные тесты на garage61 | T-105 |

### E2 · Агенты

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-201` | agents/state.py, graph.py, runtime.py (события, бюджет), MemorySaver в тестах | граф компилируется; прогон на заглушках LLM проходит все узлы | T-101, T-005 |
| `T-202` | Analyst + prompts/analyst/*.md + guard() | на 3 dev-брифах: валидный патч, ISO-001/003 <= 15% нарушений | T-201 |
| `T-203` | Modeler: процессы (DSL), DBML; самоисправление по ошибкам компилятора | SCH-002 100% после <= 3 попыток; SND-001 >= 80% | T-201, T-106 |
| `T-204` | Standards: разделы SRS (минимум), глоссарий | TPL-001 >= 80% на dev | T-201 |
| `T-205` | Reviewer, RepairTask, ci_gate, route_tasks, детектор повторов | цикл сходится или останавливается с needs_human; тест на зацикливание | T-202, T-203 |
| `T-206` | CLI reqgraph run --brief; запись кассет; README-гиф | end-to-end на 3 dev-сценариях; M2 демо | T-205 |

### E3 · Интервью и данные

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-301` | coverage.py, Interviewer, await_answer (interrupt), CLI reqgraph interview | диалог в терминале, пауза и продолжение после перезапуска | T-201 |
| `T-302` | sim/stakeholder.py: 3 персоны, правило раскрытия, другая семья моделей | ручная проверка 3 диалогов: нет «подсказок» без вопроса | T-301 |
| `T-303` | 15 сценариев (5 доменов x 3 размера), hidden.yaml 25-60 требований, persona.yaml | [you] домены и проверка эталонов; часть требований из набора PURE | — |
| `T-304` | evals/metrics: recall (эмбеддинги + судья + ручная выборка 20%), остальные метрики | results.csv; согласие судьи с ручной разметкой >= 0.8 | T-302, T-303 |

### E4 · Экспорт и evals

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-401` | exporters/srs: MD + DOCX по standards/iso29148_srs.yaml | структура разделов, ссылки на id, таблица трассировки | T-204 |
| `T-402` | exporters/tz_gost: DOCX (docxtpl) по standards/gost34_602.yaml | [you] сверить разделы с ГОСТ; TPL-002 на garage61 | T-204 |
| `T-403` | exporters/reqif | импорт в StrictDoc без ошибок | T-101 |
| `T-404` | TPL-001, TPL-002 | good/bad фикстуры | T-401, T-402 |
| `T-405` | harness: матрица; baselines B1 one-shot, B2 без CI, B3 анкета 10-15 вопросов | одинаковые входы, модель и бюджет для всех методов | T-304 |
| `T-406` | evals.yml + probe.yml с лимитом $ и артефактами | запуск из вкладки Actions | T-405 |

### E5 · Веб и деплой

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-501` | API: auth (JWKS), /projects, /runs, /runs/{id}/answer, /graph, /exports, /health | OpenAPI -> типы TS; тесты на httpx | T-206, T-004 |
| `T-502` | worker: jobs (SKIP LOCKED), PostgresSaver в схеме lg, run_events, cancel | прогон переживает рестарт процесса | T-501 |
| `T-503` | usage_daily, лимиты демо, BYOK-заголовок | 4-й прогон за день -> 429 с понятным текстом | T-501 |
| `T-504` | Web: вход, проекты, интервью-чат с Realtime | e2e: создать проект и ответить на 3 вопроса | T-501 |
| `T-505` | Web: граф (React Flow), BPMN (bpmn-js), отчёт CI, выгрузка | клик по ошибке подсвечивает узел | T-504 |
| `T-506` | Деплой: Dockerfile, Render, Vercel, Supabase prod, migrate.yml, keepalive.yml | smoke e2e на prod; замер памяти | T-505 |
| `T-507` | docker-compose.yml: офлайн-стенд + replay записанных прогонов | работает при выключенном Wi-Fi | T-506 |

### E6 · Эксперименты

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-601` | Повторный probe, фиксация профиля и версий моделей | roles.yaml заморожен до конца S6 | T-006 |
| `T-602` | Основная матрица + абляции (без покрытия, без ремонта, без TRC) | results.csv, лог расходов | T-405, T-601 |
| `T-603` | Экспертная оценка: слепые пакеты, форма, 3 эксперта | [you] найти экспертов; каппа Коэна | T-602 |
| `T-604` | Живые интервью 3-5 с согласием, сравнение с симулятором | [you] провести; анонимизация | T-301 |
| `T-605` | Статистика (Wilcoxon, размер эффекта), графики, страница /eval | H1-H4: принято / отвергнуто с p и эффектом | T-602, T-603 |

### E7 · Релиз

| ID | Задача | Критерий приёмки | Зависит |
|---|---|---|---|
| `T-701` | UML и C4 во фронтенде, документация, демо-видео 3 мин, тег v1.0 | README с результатами | T-605 |
| `T-702` | Техотчёт EN 6-8 стр.: задача, метод, эксперимент, ограничения | [you] вычитка; ссылка в CV | T-605 |
| `T-703` | Главы диплома по материалам репозитория | [you] текст пишешь ты; Claude помогает со структурой и таблицами | T-605 |

## Открытые вопросы к руководителю

- [ ] **Утвердить гипотезы H1-H4 и пороги приёмки** — или скорректировать цифры в 09_eval
- [ ] **Домены 15 сценариев** — предложение: автосервис, клиника, библиотека вуза, доставка еды, HR-онбординг
- [ ] **Объём нотаций в дипломе** — предложение: процессы + ERD в диплом; UML и C4 — в продукт; IDEF0 — после
- [ ] **Строгость структуры ТЗ** — полная структура ГОСТ 34.602-2020 или упрощённая для учебного проекта
- [ ] **Эксперты для оценки** — 3 человека: преподаватель, практикующий аналитик, магистрант
- [ ] **Язык экспериментов** — RU основной; EN-версия 3 сценариев для техотчёта
- [ ] **Живые интервью** — согласие участников, анонимизация, хранение записей

## Глоссарий

| Термин | Что это |
|---|---|
| `БТ / ПТ / ФТ / НФТ` | бизнес-, пользовательские, функциональные и нефункциональные требования |
| `SRS` | спецификация требований к ПО по ISO/IEC/IEEE 29148 |
| `ТЗ` | техническое задание по ГОСТ 34.602-2020 |
| `EARS` | шаблоны формулировок «When ... the system shall ...» |
| `Soundness` | процесс всегда может завершиться, нет тупиков и мёртвых задач |
| `DSL` | предметный язык; здесь — JSON-описание процесса для компиляции в BPMN |
| `Чекпоинтер` | сохранение состояния LangGraph после каждого узла для паузы и продолжения |
| `RLS` | row level security: правила доступа к строкам в Postgres |
| `Probe` | наш мини-бенчмарк для выбора моделей по ролям |
| `BYOK` | bring your own key: пользователь демо использует свой ключ API |

## Источники

- [Supabase: IPv4 и IPv6, pooler для Render / Vercel](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP)

- [Supabase: тарифы и лимиты](https://supabase.com/pricing)

- [Render: бесплатные инстансы](https://render.com/docs/free)

- [Vercel: тариф Hobby](https://vercel.com/docs/plans/hobby)

- [OpenRouter: сравнение бесплатных LLM API (2026)](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)

- [Бесплатные модели OpenRouter (июнь 2026)](https://aitoolsradar.org/blog/guides/openrouter-free-models-2026/)

- [Codersera: самые дешёвые near-frontier модели (авг. 2026)](https://codersera.com/blog/cheapest-near-frontier-ai-models-2026/)

- [BetterClaw: дешёвые модели для агентов (окт. 2026)](https://www.betterclaw.io/blog/cheapest-ai-models-for-agents)

- [Kroki: поддерживаемые нотации](https://kroki.io/)

- [Amvera: тарифы (ToolFox, сент. 2026)](https://toolfox.ru/services/s/amvera)

- [iReDev: multi-agent requirements development (arXiv 2507.13081)](https://arxiv.org/html/2507.13081)

- [ReqInOne: LLM-агент для SRS (arXiv 2508.09648)](https://arxiv.org/html/2508.09648)

- [BEF4LLM: BPMN-компетенции LLM (arXiv 2601.21787)](https://arxiv.org/html/2601.21787v1)

- [PM4Py: process mining и soundness](https://pm4py.fit.fraunhofer.de/)

<sub>Цены, лимиты и названия моделей — по открытым источникам на октябрь 2026, их нужно перепроверять. Оценки трудоёмкости и стоимости — расчёт, а не измерение. Пример «Гараж 61» условный.</sub>
