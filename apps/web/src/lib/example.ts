// The worked example of the landing page (T-509): real pairs «what the client said → the requirement» from
// the reference project examples/garage61 (requirements/*.yaml, derived_from → interview/transcript.jsonl).
// The company and the numbers there are made up («пример условный»); nothing here is invented on top.

export type ExamplePair = { id: string; said: string; spec: string; plain: string };

export const EXAMPLE_NAME = "автосервис «Гараж 61»";

export const PAIRS: ExamplePair[] = [
  {
    id: "BR-001",
    said: "Неявки. Примерно 15% слотов пропадают: клиент записался и не приехал. Хотим снизить хотя бы вдвое, до 7%.",
    spec: "Доля неявок клиентов должна снизиться с 15% до 7% записей в течение 6 месяцев после запуска системы.",
    plain: "Неявок станет вдвое меньше",
  },
  {
    id: "FR-013",
    said: "Второму сказать, что время уже заняли, и сразу показать ближайшие свободные варианты.",
    spec: "Если выбранный слот занял другой клиент до подтверждения записи, система должна предложить клиенту три ближайших свободных слота той же услуги.",
    plain: "Время заняли — сразу видны другие",
  },
  {
    id: "FR-014",
    said: "Администратор переносит его записи на другого мастера той же специализации, а клиентам уходит SMS.",
    spec: "Если мастер не вышел на смену, система должна позволить администратору перенести его записи на другого мастера той же специализации.",
    plain: "Мастер заболел — записи переносятся",
  },
];

/** Section 4 of the example ТЗ: the statements as the export writes them, with their sources. */
export const EXAMPLE_TZ: ExamplePair[] = [
  {
    id: "FR-002",
    said: "Время показывать на две недели вперёд, дальше мастера смены не планируют.",
    spec: "Когда клиент выбрал услугу, система должна показать свободные слоты на 14 дней вперёд с учётом длительности услуги и смен мастеров.",
    plain: "",
  },
  {
    id: "FR-007",
    said: "SMS за сутки до визита. Отменить можно, но не позже чем за 2 часа.",
    spec: "За 24 часа до начала записи система должна отправить клиенту SMS-напоминание с датой, временем и адресом.",
    plain: "",
  },
  PAIRS[1],
  PAIRS[2],
];

/** Kept across the sign-in so the project starts from what the visitor already typed. */
export const START_KEY = "sg-start";
