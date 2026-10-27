# Интервью с симулятором заказчика

| Сценарий | Характер | Повтор | Вопросов | Конец | Рассказано | Упомянуто | Неверных | Вне области | Требований | Ошибок | Вызовов LLM | Токены | Время, с | Ошибка |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev-02 | cooperative | 1 | 12 | limit | 11/28 (39%) | 0 | 0 | 0 | 0 | 0 | 57 | 183397 | 318.5 | UnexpectedModelBehavior: Invalid response from openai chat completions endpoint: 2 validation errors for ChatCompletion
choices.0.finish_reason
  Input should be 'stop', 'length', 'tool_calls', 'content_filter' or 'function_call' [type=literal_error, input_value='content_filter: PROHIBITED_CONTENT', |
