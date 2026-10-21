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
