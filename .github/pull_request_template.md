## Задача

Closes #<номер issue> · T-xxx — <название>

## Что сделано

-

## Как проверить

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/core
# pnpm -C apps/web lint && pnpm -C apps/web build   # если задета apps/web
```

## Definition of Done

- [ ] критерии приёмки задачи из docs/backlog.md выполнены
- [ ] сначала тесты, потом код; юнит-тесты без сети
- [ ] pytest, ruff, mypy зелёные (и pnpm lint/build, если задета apps/web)
- [ ] пункты DoD отмечены в docs/backlog.md
- [ ] запись в docs/journal.md, строка в CHANGELOG.md (Unreleased)
- [ ] examples/garage61 не изменён
- [ ] секретов и .env в диффе нет

## Новые зависимости

| Пакет | Версия | Лицензия | Зачем | Вес / память |
|---|---|---|---|
| — | | | | |

## Архитектура

Затронутые ADR: — · Публичные схемы (GraphPatch, CIReport, DSL, формат проекта): не меняются / меняются (версия, миграция фикстур)

## Допущения и что дальше

-
