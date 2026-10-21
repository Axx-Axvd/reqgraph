# ADR-007: Хранение и авторизация в Supabase

- Статус: принято; сужено [ADR-015](015-demo-streamlit.md) — только Postgres
- Дата: 2026-10-20
- Источник: docs/tech-design/README.md, таблица «Ключевые решения»

## Решение

Хранение: Supabase (Postgres jsonb-ревизии, Auth, Storage, Realtime).

## Почему

бесплатно, RLS из коробки, локальный стек через Supabase CLI.

## Рассмотренные альтернативы

- SQLite + файлы — нет авторизации и realtime для веб-демо
- Firebase — нет Postgres и SQL-миграций
- Neon + Clerk — два сервиса вместо одного

## Последствия

Postgres с RLS, Auth, Storage и Realtime бесплатно; локально тот же стек через Supabase CLI; бесплатный проект засыпает через 7 дней без активности.
