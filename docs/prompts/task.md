# Выполнение задачи T-xxx

1. Прочитай задачу в docs/backlog.md (и её issue на GitHub), связанные разделы docs/tech-design/ и ADR.
2. Покажи план: файлы, публичные интерфейсы, тесты (включая фикстуры good/bad для проверок), риски. Если меняются схемы, зависимости или архитектура — жди «ок».
3. Ветка feat/T-xxx. Сначала тесты, потом реализация. Маленькие коммиты в Conventional Commits.
4. Прогони: uv run pytest -q; uv run ruff check . и ruff format --check .; uv run mypy packages/core.
5. Отметь выполненные пункты Definition of Done в docs/backlog.md, добавь запись в docs/journal.md, обнови CHANGELOG.md (Unreleased).
6. Открой PR по шаблону. В конце: что сделано, как проверить вручную, принятые решения и допущения, что предлагаешь следующим. Не трогай файлы вне задачи и examples/garage61.
