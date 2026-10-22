# apps/web

Next.js (App Router, TypeScript strict) для публичного демо reqgraph. Деплой — Vercel (ADR-008).
Пока заглушка: интерфейс делается в S5 (T-504, T-505).

```bash
pnpm install              # из корня репозитория
pnpm -C apps/web dev      # http://localhost:3000
pnpm -C apps/web lint
pnpm -C apps/web build
```

Версии закреплены точно. TypeScript 6.0.3 и ESLint 9.39.5, а не 7.x и 10.x: плагины
eslint-config-next 16.4.2 (typescript-eslint, eslint-plugin-react и др.) пока не поддерживают
TypeScript ≥ 6.1 и ESLint 10 (проверено 2026-10-22).
