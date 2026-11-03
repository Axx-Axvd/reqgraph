# Analyst на dev-брифах

Прогонов: 15; требований: 269; с нарушениями ISO-001/003: 5 (2%); порог T-202 — не больше 15%, все патчи применены: да.

| Сценарий | Повтор | Модель | Применён | Повтор запроса | Отброшено | Требований | Нарушений | Доля | ISO-001 | ISO-003 | TRC-006 | Токены | Время, с | Ошибка |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev-01 | 1 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 10 | 1 | 10% | 1 | 0 | 0 | 4674 | 4.7 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-01 | 2 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 9 | 0 | 0% | 0 | 0 | 0 | 4204 | 3.7 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-01 | 3 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 8 | 1 | 12% | 1 | 0 | 0 | 4043 | 3.4 |  |
| dev-01 | 4 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 8 | 0 | 0% | 0 | 0 | 0 | 4153 | 3.4 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-01 | 5 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 11 | 0 | 0% | 0 | 0 | 0 | 4760 | 4.6 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-02 | 1 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 16 | 0 | 0% | 0 | 0 | 0 | 5945 | 7.6 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-02 | 2 | gemini/gemini-3.5-flash-lite | да | да | 1 | 24 | 0 | 0% | 0 | 0 | 0 | 13734 | 17.6 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-02 | 3 | gemini/gemini-3.5-flash-lite | да | да | 1 | 26 | 1 | 4% | 1 | 0 | 0 | 12782 | 15.6 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-02 | 4 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 13 | 1 | 8% | 1 | 0 | 0 | 5504 | 6.7 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-02 | 5 | gemini/gemini-3.5-flash-lite | да | да | 7 | 19 | 0 | 0% | 0 | 0 | 0 | 10278 | 9.9 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-03 | 1 | gemini/gemini-3.5-flash-lite | да | да | 1 | 27 | 0 | 0% | 0 | 0 | 0 | 14153 | 17.4 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-03 | 2 | gemini/gemini-3.5-flash-lite | да | да | 1 | 25 | 0 | 0% | 0 | 0 | 0 | 13830 | 17.9 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-03 | 3 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 25 | 0 | 0% | 0 | 0 | 0 | 7509 | 10.7 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-03 | 4 | gemini/gemini-3.5-flash-lite | да | нет | 0 | 23 | 0 | 0% | 0 | 0 | 0 | 6471 | 8.1 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |
| dev-03 | 5 | gemini/gemini-3.5-flash-lite | да | да | 1 | 25 | 1 | 4% | 1 | 0 | 0 | 14779 | 19.3 |  judge: ModelRateLimitError: status_code: 429, model_name: gemini-embedding-001, body: {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor you |

## Факты брифа и разброс ФТ (T-311)

Правило T-311 на бриф: худший повтор — не меньше 80% фактов брифа, ФТ max/min — не больше 2; доля нарушений ISO-001/003 сравнивается с замером до правки.

| Сценарий | Прогонов | Факты брифа: медиана | худший | ФТ по повторам | max/min ФТ | Доля нарушений | Правило |
|---|---|---|---|---|---|---|---|
| dev-01 | 1 | 100% | 100% | 3 | 1.0 | 12% | да |
| dev-02 | 0 | — | — | — | — | — | нет |
| dev-03 | 0 | — | — | — | — | — | нет |

| Сценарий | Повтор | БТ | ПТ | ФТ | НФТ | Огр. | Фактов брифа | Найдено | Частично | Не найдены | Отсеяно кодом |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev-01 | 1 | 2 | 3 | 5 | 0 | 0 | 5 | 0 | 0 |  |  |
| dev-01 | 2 | 2 | 3 | 4 | 0 | 0 | 5 | 0 | 0 |  |  |
| dev-01 | 3 | 2 | 3 | 3 | 0 | 0 | 5 | 5 | 0 |  |  |
| dev-01 | 4 | 2 | 3 | 3 | 0 | 0 | 5 | 0 | 0 |  |  |
| dev-01 | 5 | 2 | 3 | 6 | 0 | 0 | 5 | 0 | 0 |  |  |
| dev-02 | 1 | 1 | 4 | 9 | 1 | 1 | 12 | 0 | 0 |  |  |
| dev-02 | 2 | 4 | 5 | 13 | 1 | 1 | 12 | 0 | 0 |  | link n28 refines n7: такая связь недопустима |
| dev-02 | 3 | 2 | 10 | 12 | 1 | 1 | 12 | 0 | 0 |  | link n26 refines n2: такая связь недопустима |
| dev-02 | 4 | 1 | 4 | 6 | 1 | 1 | 12 | 0 | 0 |  |  |
| dev-02 | 5 | 2 | 5 | 9 | 1 | 2 | 12 | 0 | 0 |  | link n9 refines n5: такая связь недопустима | link n12 refines n19: такая связь недопустима | link n12 refines n20: такая связь недопустима | link n13 refines n21: такая связь недопустима | link n13 refines n20: такая связь недопустима | link n14 refines n22: такая связь недопустима | link n14 refines n23: такая связь недопустима |
| dev-03 | 1 | 1 | 10 | 11 | 3 | 2 | 16 | 0 | 0 |  | link n11 refines n9: такая связь недопустима |
| dev-03 | 2 | 2 | 9 | 9 | 3 | 2 | 16 | 0 | 0 |  | ur_loan_teacher «Правила выдачи и продления для преподавателей»: ни одно ФТ не уточняет это ПТ — добавь его в refines тех FR, которые уже описывают нужные действия системы (у FR может быть несколько родителей), а недостающие действия из его сценария запиши новыми FR; одно и то же действие для разных ролей — одно FR |
| dev-03 | 3 | 2 | 9 | 9 | 2 | 3 | 16 | 0 | 0 |  |  |
| dev-03 | 4 | 2 | 8 | 8 | 3 | 2 | 16 | 0 | 0 |  |  |
| dev-03 | 5 | 2 | 9 | 9 | 3 | 2 | 16 | 0 | 0 |  | link n27 refines n7: такая связь недопустима |
