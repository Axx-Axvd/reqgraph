<sub>reqgraph · tech design v1.0 · [README](README.md) · [01_why](01_why.md) · [02_arch](02_arch.md) · [03_agents](03_agents.md) · [04_data](04_data.md) · [05_ci](05_ci.md) · [06_models](06_models.md) · [07_deploy](07_deploy.md) · [08_plan](08_plan.md) · [09_eval](09_eval.md) · [10_claude](10_claude.md)</sub>

# 10 Claude Code

*как вести разработку с ИИ-ассистентом: правила, бэклог, промпты*

## Процесс

`1.` Публичный репозиторий reqgraph (MIT): CLAUDE.md в корне, Markdown-версия плана — в docs/tech-design/ (главная), PDF — в docs/tech-design.pdf (снимок на 20.10.2026, может отставать).

`2.` Одна задача T-xxx = одна сессия = одна ветка и PR. Не проси «сделать всё сразу».

`3.` Начинай сессию в режиме плана: Claude Code читает задачу и связанные разделы, показывает файлы, интерфейсы и тесты.

`4.` Сначала тесты, потом код. После задачи: pytest, ruff, mypy зелёные; отметь пункт Definition of Done в docs/backlog.md (чек-листы DoD живут там; в 08_plan — только план).

`5.` Задачи с пометкой [you] требуют твоего решения или участия: домены сценариев, эксперты, текст диплома.

## Шаблоны промптов

Постоянные версии — в [docs/prompts/](../prompts/); ниже — примеры коротких запросов.

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

## CLAUDE.md и бэклог

Копий здесь больше нет: раньше они расходились с оригиналами. Актуальные версии — в репозитории:

- правила для Claude Code — [CLAUDE.md](../../CLAUDE.md);
- задачи, критерии приёмки и Definition of Done — [docs/backlog.md](../backlog.md) (и issues на GitHub);
- постоянные инструкции сессий — [docs/prompts/](../prompts/): `preflight.md`, `task.md`, `review.md`, `debug.md`;
- дневник решений — [docs/journal.md](../journal.md).

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

- [Supabase: IPv4 и IPv6, session pooler](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP)

- [Supabase: тарифы и лимиты](https://supabase.com/pricing)

- [Streamlit Community Cloud: ресурсы и сон приложений](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)

- [pydantic-ai: модели, FallbackModel, structured output](https://ai.pydantic.dev/)

- [Render: бесплатные инстансы](https://render.com/docs/free) (запасной вариант)

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
