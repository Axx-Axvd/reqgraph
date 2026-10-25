# Интервью с симулятором заказчика

| Сценарий | Характер | Повтор | Вопросов | Конец | Рассказано | Упомянуто | Неверных | Вне области | Требований | Ошибок | Вызовов LLM | Токены | Время, с | Ошибка |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev-01 | cooperative | 1 | 18 | — | 12/20 (60%) | 0 | 0 | 13 | 0 | 0 | 72 | 296379 | 1097.4 | UnexpectedModelBehavior: Invalid response from openai chat completions endpoint: 3 validation errors for ChatCompletion
choices
  Input should be a valid list [type=list_type, input_value=None, input_type=NoneType]
    For further information visit https://errors.pydantic.dev/2.14/v/list_type
model
 |
| dev-01 | vague | 1 | 3 | — | 2/20 (10%) | 3 | 0 | 1 | 0 | 0 | 12 | 39849 | 126.5 | FallbackExceptionGroup: All models from FallbackModel failed (3 sub-exceptions) |
| dev-01 | contradictory | 1 | 0 | — | 0/20 (0%) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | FallbackExceptionGroup: All models from FallbackModel failed (3 sub-exceptions) |
