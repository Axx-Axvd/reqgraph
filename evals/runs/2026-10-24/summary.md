# Прогоны `reqgraph run` на 3 dev-брифах (T-206, 24.10.2026)

Каждый проект создан командами из [docs/demo/m2.md](../../../docs/demo/m2.md):

```
uv run reqgraph init evals/runs/2026-10-24/dev-0N --name "<название из брифа>" --brief evals/scenarios/dev-0N/brief.md
uv run reqgraph run evals/runs/2026-10-24/dev-0N
uv run reqgraph bpmn <процесс.process.json> -o <процесс.bpmn>   # для просмотра в Camunda Modeler
```

Профиль free, ремонт с Reviewer на LLM (`--reviewer llm`), не больше 5 кругов (checks.max_iterations по умолчанию), бюджет $0.50 на прогон.
Код — ветка feat/T-206 поверх main aa58e33 (до коммита), пакет 0.1.0. По одному прогону на бриф:
это демо M2, а не замер — доли и повторы считают `reqgraph-evals` (evals/reports/).

Все числа ниже — из `dev-0N/reports/run-summary.json` и `run-events.jsonl`.

| Бриф | Требований | Ролей | Процессов | Сущностей | Разделов SRS | Ошибок в начале → в конце | Предупреждений | Кругов ремонта | Вызовов LLM | Токенов (вход + выход) | $ | Время, с | Код выхода |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev-01 | 12 | 2 | 3 | 4 | 15 | 1 → 0 | 2 | 1 | 7 | 17676 + 6466 | 0 | 76.0 | 0 |
| dev-02 | 20 | 4 | 5 | 6 | 15 | 11 → 0 | 9 | 1 | 6 | 16506 + 10306 | 0 | 55.9 | 0 |
| dev-03 | 20 | 4 | 4 | 5 | 15 | 0 → 0 | 10 | 0 | 5 | 21948 + 12945 | 0 | 49.0 | 0 |

Что происходило (события из `run-events.jsonl`):

- **dev-01.** Самопроверка Modeler: попытка 1 — 7 проблем, попытка 2 — 11, попытка 3 — 0. Проверки:
  1 ошибка TPL-001 (пустой раздел SRS из графа) → Reviewer отдал её Analyst → после круга 0 ошибок.
- **dev-02.** Modeler чист с первой попытки. Проверки: 11 ошибок ISO-003 (размытые формулировки);
  Reviewer собрал 10 задач (предел за круг) → Analyst переписал требования → 0 ошибок.
- **dev-03.** Самопроверка Modeler: 10 → 29 → 0 проблем за 3 попытки; проверки сразу без ошибок,
  ремонт не понадобился.

Модели (`models` в run-summary.json): Analyst и Modeler — gemini/gemini-3.5-flash-lite, Standards и
Reviewer — groq/openai/gpt-oss-120b. Хэши промптов: analyst/extract 5cf909f1733c, modeler/model
87f1cac3ef8e, standards/srs 85d428c41ab0, reviewer/review 435e145d20b1. Температура 0.2 и seed 42 —
из `llm/roles.yaml` (defaults; seed к Gemini не уходит: `supports_seed: false`); поля `temperature`
и `seeds` в run-summary.json добавлены после этих прогонов, в их файлах их нет.

Повторная проверка сохранённых проектов `reqgraph check <проект> --offline`: 0 ошибок у всех трёх.
TPL-001 при этом пропускается: разделы SRS (SEC) живут в графе прогона, FileStore их пока не хранит
(экспорт документов — T-401).

Сквозной тест на кассете (`packages/core/tests/agents/test_run_live.py`) записан отдельным, четвёртым
прогоном на dev-01; его числа здесь не учтены.
