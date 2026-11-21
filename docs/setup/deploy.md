# Публикация демо (T-506): Supabase, Render, Vercel

Инструкция для автора: что сделать один раз, чтобы reqgraph открывался по ссылке. Всё на бесплатных тарифах, регион — Франкфурт (решение автора 21.11).

После настройки обновления идут сами:
- **Сервер** (Render) пересобирается после мержа в main.
- **Сайт** (Vercel) — тоже.
- **Миграции базы** накатывает `migrate.yml`, после вашего подтверждения в GitHub.

Ключи вводятся только в настройках сервисов. В чат, в репозиторий и в issue их не писать.

Порядок важен: адреса из одного шага нужны в следующем. Займёт около получаса.

## 1. Supabase — база, вход, хранилище

1. https://supabase.com/dashboard → **New project**: имя `reqgraph-prod`, регион **Central EU (Frankfurt)**. Пароль базы сохраните в менеджере паролей: он нужен в шагах 2 и 3.
2. Когда проект создан, выпишите:

   | Что | Где в панели | Куда пойдёт |
   |---|---|---|
   | адрес проекта `https://<ref>.supabase.co` и `ref` | Project Settings → General / API | Render, Vercel, GitHub |
   | ключ `anon` (или publishable) | Project Settings → API Keys | Vercel (это открытый ключ) |
   | ключ `service_role` (или secret) | там же | только Render |
   | строка подключения **Session pooler**, порт 5432 | кнопка **Connect** → Session pooler | Render, `DATABASE_URL` |

3. **Ключи подписи входа.** Authentication → JWT Keys (Signing Keys). Должен быть включён асимметричный ключ (ECC P-256 или RSA). Сервер проверяет вход по `/auth/v1/.well-known/jwks.json`. Если там только старый общий секрет (Legacy JWT secret), нажмите миграцию на новые ключи.

Адрес и `ref` проекта можно прислать в чат, они не секретные. Ключи присылать не нужно.

## 2. GitHub — миграции и проверки

Репозиторий → **Settings**:

1. **Environments** → New environment `production` → Required reviewers: вы.
2. **Secrets and variables → Actions → Secrets:**
   - `SUPABASE_ACCESS_TOKEN` — https://supabase.com/dashboard/account/tokens → Generate new token;
   - `SUPABASE_DB_PASSWORD` — пароль базы из шага 1.
3. **Secrets and variables → Actions → Variables:**
   - `SUPABASE_PROJECT_REF` — `ref` проекта.

   Добавятся позже, в шаге 6:
   - `PROD_API_URL` — адрес сервера на Render;
   - `PROD_WEB_URL` — адрес сайта на Vercel.
4. **Actions → migrate → Run workflow.** Подтвердите запуск, когда GitHub попросит: окружение `production`. Workflow создаст таблицы, политики доступа и бакет `exports`. В шаге «what will be applied» видно, какие миграции он применит.

## 3. Render — сервер с исполнителем

1. https://dashboard.render.com → **New → Blueprint** → репозиторий `reqgraph`. Render прочитает `render.yaml`: сервис `reqgraph-api`, Docker, Frankfurt, Free.
2. Заполните переменные, помеченные к вводу:

   | Переменная | Значение |
   |---|---|
   | `DATABASE_URL` | строка Session pooler из шага 1, с паролем базы |
   | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `SUPABASE_JWKS_URL` | `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` |
   | `SUPABASE_SERVICE_ROLE_KEY` | ключ `service_role` |
   | `CORS_ORIGINS` | пока пусто; адрес сайта впишете в шаге 5 |
   | `OPENROUTER_API_KEY` | ключ OpenRouter: на нём работают модели демо (профиль `cheap`) |
   | `GEMINI_API_KEY` | ключ Google AI Studio (запас для `cheap`) |
   | `GROQ_API_KEY` | ключ Groq (профиль `free`, на него демо переходит после потолка $0,20 в день) |

3. **Apply.** Первая сборка образа идёт 5–10 минут. Проверка: `https://<сервис>.onrender.com/health` отвечает `{"status": "ok", "database": true, …}`.

У OpenRouter ключу можно задать месячный лимит в долларах. Для демо разумно $6: столько выходит при потолке $0,20 в день.

## 4. Vercel — сайт

1. https://vercel.com → **Add New → Project** → репозиторий `reqgraph`.
2. **Root Directory:** `apps/web`. Framework определится сам (Next.js), pnpm — по `pnpm-lock.yaml`.
3. **Environment Variables:**

   | Переменная | Значение |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ключ `anon` (не `service_role`) |
   | `NEXT_PUBLIC_API_URL` | `https://<сервис>.onrender.com` |

4. **Deploy.** Сайт получит адрес вида `https://reqgraph-<...>.vercel.app`.

## 5. Связать адреса и включить вход

1. **Render** → сервис → Environment: `CORS_ORIGINS` = адрес сайта на Vercel, без `/` в конце. Сервис перезапустится сам.
2. **Supabase** → Authentication → URL Configuration:
   - Site URL — адрес сайта;
   - Redirect URLs — `https://<сайт>.vercel.app/auth/callback`.
3. **Вход через GitHub.**
   1. https://github.com/settings/developers → **New OAuth App**. Укажите:
      - Homepage URL — адрес сайта;
      - Authorization callback URL — `https://<ref>.supabase.co/auth/v1/callback`.
   2. Скопируйте Client ID и создайте Client secret.
   3. Supabase → Authentication → Sign In / Providers → **GitHub** → включить, вставить оба значения.
4. **Вход по ссылке на почту** работает сразу. Встроенная почта Supabase отправляет всего несколько писем в час; для демо этого хватает.

## 6. Проверка

1. GitHub → Settings → Variables: `PROD_API_URL` и `PROD_WEB_URL`.
2. **Actions → smoke → Run workflow.** Playwright откроет настоящий сайт и проверит:
   - страницу входа и дисклеймер;
   - `/health` и доступ к API со страницы сайта (CORS);
   - 401 без входа;
   - кнопку GitHub.

   Память сервера будет в сводке запуска.
3. **Ваш прогон** — один раз руками: войти через GitHub → создать проект с брифом → «Начать интервью» → ответить на 3 вопроса → «Готово» → открыть «Граф», «Проверки», «Выгрузка» → «Сделать документы» → скачать SRS.
4. **Роль администратора** (без лимита «3 прогона в день»). Supabase → Table Editor → `profiles` → в своей строке `role` = `admin`.

После этого напишите в чат «демо готово». Я посмотрю сводку smoke и пик памяти и запишу результат.

## Что работает само

| Что | Когда | Где |
|---|---|---|
| Сборка сервера | push в main | Render, `apps/api/Dockerfile` |
| Сборка сайта | push в main, превью на PR | Vercel |
| Миграции | push в main с изменениями `supabase/migrations/` | `migrate.yml`, после вашего подтверждения |
| Smoke | после миграций и по кнопке | `smoke.yml` |
| Пробуждение | раз в 3 дня | `keepalive.yml`: Render спит после 15 минут без запросов, Supabase — после недели без активности |
| Очистка | при старте сервера и раз в сутки | выгрузки старше 30 дней, события прогонов старше 30 дней, чекпоинты прогонов, завершённых больше 14 дней назад |

## Если что-то не так

| Признак | Причина и что сделать |
|---|---|
| `/health` — `"database": false` | неверная `DATABASE_URL`: нужна строка **Session pooler** (порт 5432), а не прямое подключение (IPv6) |
| на сайте «Не получилось» при любом действии | `CORS_ORIGINS` не совпадает с адресом сайта или `NEXT_PUBLIC_API_URL` указывает не туда |
| после входа снова страница входа | в Supabase нет `…/auth/callback` в Redirect URLs |
| API отвечает 401 на всё после входа | JWKS пуст: в проекте старый общий секрет. Включите асимметричные ключи (шаг 1.3) |
| «Сделать документы» — 503 | на Render не заданы `SUPABASE_URL` или `SUPABASE_SERVICE_ROLE_KEY` |
| сервер перезапускается во время прогона | не хватило памяти (512 МБ). Пик видно в `/health` и в журнале Render (`peak memory`); напишите в чат |
