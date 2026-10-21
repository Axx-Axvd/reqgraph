# garage61 — эталонный проект

Условный автосервис «Гараж 61» в формате docs-as-code: интервью, требования, процессы, модель данных, UML, C4 и трассировка. На этом примере тестируется ядро reqgraph: чтение и запись проекта, компилятор BPMN, все проверки и экспорт.

**Статус: черновик.** Перед использованием в тестах его нужно проверить по [REVIEW.md](REVIEW.md).

```text
garage61/
├── reqgraph.yaml          # настройки проекта
├── brief.md               # бриф заказчика
├── interview/             # transcript.jsonl, coverage.json (сгенерирован)
├── requirements/          # actors, business, user, functional, nonfunctional, constraints
├── models/
│   ├── processes/         # PRC-01 онлайн-запись, PRC-02 напоминание и отмена (JSON DSL)
│   ├── data/erd.dbml
│   ├── uml/               # use_cases.puml, seq_booking.puml
│   └── c4/workspace.dsl
├── trace/edges.yaml       # сгенерирован из requirements/
├── reports/               # сюда пишет reqgraph check
└── exports/               # сюда пишет reqgraph export
```

После T-107: `uv run reqgraph check examples/garage61` должен завершаться без ошибок.
