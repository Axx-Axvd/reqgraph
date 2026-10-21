# Версии зависимостей и ключевые API — октябрь 2026

Дата проверки: **2026-10-21**. Как проверяли:
- версии и лицензии — PyPI JSON API (`pypi.org/pypi/<pkg>/json`) и npm registry;
- API — импорт и `inspect` в чистом venv (Python 3.12.13, облачная VM);
- память — `VmRSS` до и после импорта в отдельном процессе.

Вывод установки и замеров воспроизводится скриптом из раздела «Как повторить».

## Python

| Пакет | Последняя | Дата | Лицензия | Расходится с docs? | Что поменять |
|---|---|---|---|---|---|
| langgraph | 1.2.16 | 2026-10-16 | MIT | нет: `StateGraph`, `START/END`, `langgraph.types.interrupt`, `Command(resume=, goto=, update=)`, `compile(checkpointer=…)` на месте; `MemorySaver` — алиас `InMemorySaver` | в T-201 писать `InMemorySaver`; тянет `langchain-core` 1.6 (+68 МБ при импорте, см. ниже) — это не нарушает ADR-003 (обёртки моделей LangChain мы не используем), но учитываем в памяти |
| langgraph-checkpoint-postgres | 3.2.0 | 2026-10-14 | MIT | **да:** `PostgresSaver.setup()` создаёт таблицы `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` **без схемы**, в текущем `search_path` | «схема lg» из 04_data требует `search_path=lg` на соединениях чекпоинтера. Через Supavisor надёжнее отдельный пул с `configure=lambda c: c.execute("set search_path to lg")`, чем параметр `options` в строке подключения — проверить в T-502 |
| instructor | 1.17.0 | 2026-09-09 | MIT | **да:** требует `jiter<0.15`, а openai ≥ 3.36 — `jiter>=0.16`. С instructor резолвер ставит **openai 3.3.0** вместо 3.36.0; плюс тянет `aiohttp`, `requests`, `typer`, `rich<15`; `instructor.from_openai()` добавляет ~75 МБ | предложен [ADR-013](../adr/013-structured-output-without-instructor.md): structured output через `client.chat.completions.parse(response_format=Model)` / `response_format={"type":"json_schema"}` + свой ретрай на tenacity |
| openai | 3.36.0 | 2026-10-21 | Apache-2.0 | major-версия 3 (в docs версия не указана); есть `chat.completions.parse` и `responses` | Chat Completions — единственный API, общий для OpenRouter, Groq, Gemini и Ollama; Responses API не используем |
| pydantic | 2.14.1 | 2026-10-11 | MIT | нет | — |
| pydantic-settings | 2.16.1 | 2026-10-20 | MIT | нет (Python ≥ 3.11) | T-501 |
| fastapi / uvicorn | 0.158.1 / 0.54.0 | 2026-10 / 2026-09 | MIT / BSD | нет | T-501; не ставить в T-001 |
| **pm4py** | 2.7.23.11 | 2026-10-15 | **AGPL-3.0-or-later** | **да, три расхождения:** (1) лицензия AGPL при MIT-репозитории и публичном веб-демо; (2) импорт +160 МБ RSS и 5,6 с (тянет pandas, scipy, matplotlib, cvxopt, graphviz); (3) конвертер BPMN → сеть Петри (`objects/conversion/bpmn/variants/to_petri_net.py`) обрабатывает только Task, Start/End, Exclusive/Parallel/Inclusive — **`EventBasedGateway` и промежуточные события (timer, message) пропускает**, а они есть в PRC-02 эталона | предложен [ADR-014](../adr/014-own-soundness-check.md): своя проверка soundness по DSL; pm4py — только dev-зависимость для перекрёстной проверки в тестах |
| pydbml | 1.2.1 | 2025-10-24 | MIT | нет | T-104 |
| docxtpl / python-docx | 0.20.2 / 1.2.0 | 2025 | LGPL-2.1 / MIT | нет; LGPL совместима с использованием как библиотеки | T-402 |
| reqif | 0.1.0 | 2026-08-11 | Apache-2.0 | нет; версия 0.x — API может меняться | T-403, закрепить версию |
| strictdoc | 0.30.3 | 2026-10-18 | Apache-2.0 | — | только для проверки импорта ReqIF (T-403), не runtime |
| typer / rich | 0.27.3 / 15.0.0 | 2026 | MIT | instructor держит `rich<15`; без instructor берём 15 | T-001 |
| networkx | 3.7 | 2026-09-21 | BSD | требует Python ≥ 3.12 — совпадает с нашим выбором | — |
| lxml | 6.1.3 | 2026-09-02 | BSD | нет | XSD BPMN (SCH-001) |
| pymorphy3 | 2.0.6 | 2025-10-09 | MIT | нет; `MorphAnalyzer()` +29 МБ | создавать один экземпляр лениво |
| rapidfuzz | 3.14.6 | 2026-08-30 | MIT | нет | — |
| tenacity | 9.2.1 | 2026-10-07 | Apache-2.0 | нет | ретраи роутера |
| tiktoken | 0.14.0 | 2026-08-17 | MIT | не нужен: провайдеры возвращают `usage` | убрать из стека (02_arch) — минус зависимость |
| psycopg | 3.3.6 | 2026-09-18 | LGPL-3.0 | нет | `psycopg[binary]`, `psycopg-pool` |
| httpx | 0.28.1 | 2024-12-06 | BSD | openai 3.36 перешёл на `httpx2` | для Kroki достаточно `httpx` |
| pytest / pytest-recording / vcrpy | 9.1.1 / 0.14.0 / 8.3.0 | 2026 | MIT | нет | кассеты: `filter_headers=["authorization","x-goog-api-key"]` |
| pytest-socket / pytest-cov | 0.8.1 / 7.1.0 | 2026 | MIT | нет | T-001 |
| hypothesis | 6.170.5 | 2026-10-20 | MPL-2.0 | нет | T-101 (свойства патчей) |
| ruff / mypy / pre-commit | 0.17.1 / 2.4.0 / 4.7.0 | 2026-10 | MIT | нет | T-001 |

## JavaScript

| Пакет | Последняя | Дата | Лицензия | Расходится с docs? | Что поменять |
|---|---|---|---|---|---|
| next | 16.4.2 | 2026-10-15 | MIT | нет; Node ≥ 20.9 | T-001: `create-next-app@16.4.2`, App Router, TS strict |
| react | 19.3.1 | 2026-10-14 | MIT | нет | — |
| typescript | **7.0.2** | 2026-07-08 | Apache-2.0 | новая major-версия (нативный компилятор); `next` не объявляет peer-зависимость, `eslint-config-next` требует `>=3.3.1` | в T-001 проверить `next build` с TS 7; если сломается — закрепить последнюю 6.x и записать в journal |
| eslint / eslint-config-next | 10.13.0 / 16.4.2 | 2026-10 | MIT | нет | flat config |
| bpmn-js | 18.31.1 | 2026-10-21 | MIT **с условием**: водяной знак bpmn.io на диаграмме нельзя убирать или перекрывать | в docs не упомянуто | T-505: не скрывать логотип bpmn.io в `BpmnViewer` |
| @xyflow/react | 12.12.0 | 2026-09-24 | MIT | нет | T-505 |
| @supabase/supabase-js | 2.118.0 | 2026-10-15 | MIT | требует **Node ≥ 22** | Node 22/24 на всех машинах (VM: 22.22, ноутбук: 24 LTS) |
| supabase (CLI) | 2.121.0 | 2026-10-14 | MIT | нет | devDependency в корне (T-004), запуск `pnpm supabase …` |
| @tanstack/react-query | 5.104.5 | 2026-10-19 | MIT | нет | S5 |
| tailwindcss | 4.3.3 | 2026-07-16 | MIT | нет | S5 (не ставить в T-001) |
| @playwright/test | 1.64.1 | 2026-10-14 | Apache-2.0 | нет | S5; в VM Chromium уже есть |

## Память импорта (Render Free, 512 МБ)

Пустой интерпретатор Python 3.12 — 11 МБ RSS. Прирост RSS после импорта:

| Импорт | +RSS | Время |
|---|---|---|
| `openai` | +58 МБ | 1,5 с |
| `instructor.from_openai(...)` (поверх openai) | +75 МБ | — |
| `pydantic` | +7 МБ | — |
| `fastapi, uvicorn` | +37 МБ | 0,7 с |
| `langgraph.graph` | +68 МБ | 1,9 с |
| `langgraph.checkpoint.postgres` | +45 МБ | 0,6 с |
| **`pm4py`** | **+160 МБ** | **5,6 с** |
| `lxml, networkx, pydbml, rapidfuzz, pymorphy3` (+ `MorphAnalyzer()` +29 МБ) | +38 МБ | 0,4 с |
| `docxtpl` | +22 МБ | 0,3 с |
| `reqif` | +2 МБ | — |
| **api + worker без pm4py и instructor** (fastapi, openai, langgraph, checkpoint-postgres, lxml, networkx) | **+121 МБ → 132 МБ** | 1,8 с |
| **всё вместе** (включая pm4py, instructor, docxtpl, reqif, pymorphy3) | **+239 МБ → 250 МБ** | 3,4 с |

**Вывод.** Импорты занимают от 132 до 250 МБ ещё до первого запроса, а рабочая память прогона (граф, промпты, ответы LLM, DOCX) добавится сверху.
- Если убрать pm4py из runtime (ADR-014) и instructor (ADR-013), остаётся ~380 МБ запаса до 512 МБ.
- С pm4py бюджет 450 МБ из DoD S5 под угрозой.
- Тяжёлое импортируем лениво: `docxtpl` — внутри экспорта, `pymorphy3` — при первом ISO-001.

## Как повторить

```bash
uv venv -p 3.12 /tmp/mem && uv pip install -p /tmp/mem langgraph langgraph-checkpoint-postgres "psycopg[binary]" pm4py openai instructor fastapi uvicorn lxml networkx pydbml docxtpl reqif pymorphy3 rapidfuzz
/tmp/mem/bin/python -c "import importlib,sys;b=lambda:[int(l.split()[1])/1024 for l in open('/proc/self/status') if l.startswith('VmRSS')][0];x=b();importlib.import_module(sys.argv[1]);print(round(b()-x,1),'MB')" pm4py
```

Полный размер venv со всеми пакетами выше — 536 МБ на диске; установка через uv — 19 с.
