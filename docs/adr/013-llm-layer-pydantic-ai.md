# ADR-013: LLM-слой на pydantic-ai

- Статус: принято (2026-10-21, решение автора: «использовать готовые средства вместо своего кода»)
- Дата: 2026-10-21
- Уточняет: [ADR-003](003-llm-router.md) — тонкий роутер остаётся, но собирается из pydantic-ai, а не из openai SDK + instructor
- Источник: [docs/research/2026-10-versions.md](../research/2026-10-versions.md), раздел «Готовые замены»

## Контекст

ADR-003 предполагал свой роутер (~200 строк): фолбэки, ретраи по ошибкам схемы, учёт $ и токенов, prices.yaml, structured output через instructor. Проверка 21.10.2026:

- instructor 1.17 несовместим с openai ≥ 3.36 (конфликт по `jiter`), тянет `aiohttp`, `requests`, `typer`; `from_openai()` +75 МБ;
- `pydantic-ai-slim[openai]` 2.59 (MIT) уже умеет всё, что мы собирались писать сами:
  - `Agent(model, output_type=Model, retries=n)` — ответ сразу в Pydantic-модель, при ошибке валидации повтор с текстом ошибки;
  - `FallbackModel(m1, m2, ...)` — переход на следующую модель при 429, 5xx, таймауте;
  - `UsageLimits(request_limit=..., total_tokens_limit=...)` — бюджет прогона;
  - `result.usage` и `result.response.cost()` через genai-prices — токены и $;
  - провайдеры OpenRouter, Groq, Google (OpenAI-совместимый), Ollama.
- Проверено вживую 21.10 на ключах автора: Groq `openai/gpt-oss-120b`, Gemini `gemini-3.5-flash-lite`, OpenRouter `minimax/minimax-m3.1-flash:free` вернули валидный объект; `FallbackModel` с несуществующей первой моделью перешёл на Groq; `cost()` посчитал цену. Импорт +57 МБ (столько же, сколько один openai SDK).

## Решение

- `llm/roles.yaml` остаётся источником правды: роль → лестница моделей (`провайдер/модель`), флаг `free: true` для бесплатных тарифов.
- `llm/router.py` (~50 строк) читает `roles.yaml` и собирает `FallbackModel` для роли; `structured(role, prompt, output_type)` = `Agent(...).run(...)` с `UsageLimits` из бюджета прогона.
- Стоимость: `response.cost()` для платных моделей, 0 — для моделей с `free: true`. prices.yaml не нужен.
- Каждый вызов пишет в лог прогона: роль, модель, провайдер, токены, $, латентность, исход.
- LangGraph (ADR-002) остаётся оркестратором; pydantic-ai используется только внутри узлов-агентов.

## Последствия

- T-005 (LLM-слой) сокращается до конфигурации и тонкой обёртки; минус instructor, tiktoken, prices.yaml.
- Кассеты pytest-recording работают: pydantic-ai ходит в сеть через httpx2.
- pydantic-ai быстро выпускает версии (2.59 на 21.10) — закрепляем версию в uv.lock, обновляем через Dependabot с прогоном кассет.
- Баннер pydantic-ai в консоли отключается переменной `PYDANTIC_AI_NO_BANNER=1`.

## Альтернативы

- Свой роутер на openai SDK + instructor (ADR-003 как есть) — больше кода, конфликт версий.
- LiteLLM — тяжелее и требует `openai<3`.
- any-llm-sdk — тянет `anthropic`, нет structured output с ретраями.
