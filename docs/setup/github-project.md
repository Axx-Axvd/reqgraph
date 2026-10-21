# Доска «reqgraph roadmap» в GitHub Projects (вручную)

Метки, вехи и задачи создаёт `scripts/github_bootstrap.py` через REST. GitHub Projects v2 доступны только через GraphQL, а GraphQL в облачных сессиях Claude Code заблокирован. Поэтому доску один раз создаёт автор в браузере (~10 минут).

## 1. Создать проект

1. github.com → аватар → **Your projects** → **New project** → шаблон **Board**.
2. Название: `reqgraph roadmap`. Видимость: **Public** (Settings проекта → Visibility), чтобы ссылку можно было дать в CV.
3. В Settings проекта → **Manage access** привязать репозиторий `Axx-Axvd/reqgraph`, чтобы проект был виден на вкладке *Projects* репозитория.

## 2. Колонки (поле Status)

Settings → Fields → **Status** → оставить ровно такие значения:

| Значение | Смысл |
|---|---|
| Backlog | задача есть, зависимости не готовы |
| Ready | зависимости закрыты, можно брать |
| In progress | открыта ветка `feat/T-xxx` |
| Review | открыт PR |
| Done | PR смёрджен |

## 3. Свои поля

Settings → Fields → **+ New field**:

| Поле | Тип | Значения |
|---|---|---|
| Спринт | Single select | S0 … S7 (можно вместо этого использовать встроенное поле Milestone) |
| Оценка, ч | Number | часы по таблице «Оценка трудоёмкости» в 08_plan.md |

## 4. Добавить все задачи

1. В проекте внизу колонки нажмите **+ Add item** → **Add item from repository** → `reqgraph` → **Select all** → **Add selected items**.
2. Либо включите автодобавление: меню проекта → **Workflows** → **Auto-add to project** → фильтр `is:issue label:epic:E0,epic:E1,epic:E2,epic:E3,epic:E4,epic:E5,epic:E6,epic:E7` → **On**.

## 5. Автоматизация (встроенные Workflows)

- **Item closed** → Status = Done.
- **Pull request merged** → Status = Done.
- **Item added to project** → Status = Backlog.
- **Item reopened** → Status = In progress.

## 6. Представления

- **Board** по Status (основное).
- **Table**, сгруппированная по Milestone, с колонками Labels и «Оценка, ч»: сумма часов по спринту.
- **Roadmap** по Milestone: даты вех M0–M7 уже заданы скриптом.

## 7. Перевести S0 в Ready

Отфильтруйте `milestone:M0` и переведите T-001 в **Ready**: у неё нет зависимостей. Остальные задачи S0 зависят от T-001 и пока остаются в Backlog.
