# ADR-013: Structured output через openai SDK без instructor

- Статус: **предложено** (ждёт решения автора)
- Дата: 2026-10-21
- Уточняет: [ADR-003](003-llm-router.md) — роутер остаётся, меняется только способ получить Pydantic-объект
- Источник: [docs/research/2026-10-versions.md](../research/2026-10-versions.md)

## Контекст

ADR-003 выбрал «тонкий роутер над openai SDK + instructor». Проверка 21.10.2026 показала:

- instructor 1.17.0 требует `jiter<0.15`, а openai ≥ 3.36 — `jiter>=0.16`. С instructor резолвер ставит openai 3.3.0 и дальше обновляться не даёт;
- instructor тянет `aiohttp`, `requests`, `typer`, `rich<15`, а `instructor.from_openai()` добавляет ~75 МБ RSS;
- все наши провайдеры (OpenRouter, Groq, Gemini через OpenAI-совместимый endpoint, Ollama) принимают `response_format` (JSON mode), а большинство кандидатов — и `json_schema` (structured outputs).

## Решение

`llm/router.py` реализует `structured(role, messages, response_model)` сам:

1. отправляет `response_format={"type": "json_schema", "json_schema": {"name": ..., "schema": Model.model_json_schema(), "strict": true}}`; если модель в `roles.yaml` помечена `so: false`, использует `{"type": "json_object"}` и схему в системном сообщении;
2. валидирует ответ `Model.model_validate_json(...)`;
3. при `ValidationError` повторяет запрос до `max_retries` раз (tenacity) с текстом ошибки в сообщении — так же, как это делает instructor;
4. затем переходит на следующую модель лестницы фолбэков.

## Последствия

- Минус одна зависимость с транзитивными пакетами и ~75 МБ памяти; openai SDK обновляется свободно.
- Около 60–80 строк своего кода и тесты на кассетах: невалидный JSON, ретрай, фолбэк.
- Нет режима `Mode.TOOLS` из instructor. Если какая-то модель не поддерживает `response_format`, это видно в probe (T-006), и такая модель просто не попадает в роли.

## Альтернативы

- Оставить instructor и закрепить openai 3.3.0 — работает, но блокирует обновления SDK и мешает Dependabot.
- LiteLLM — отвергнут ещё в ADR-003 (память).
