# Ноутбук автора (Windows 10/11, без GPU): чек-лист окружения

Проверено 2026-10-21. Источники id winget: документация uv (`docs.astral.sh/uv/getting-started/installation`), winstall.app, winget-pkgs. Перед установкой любой id можно проверить командой `winget show --id <id> -e`.

Все команды выполняются в PowerShell. После установки откройте новое окно терминала, чтобы обновился PATH.

| # | Что | Установка | Проверка | Ожидается |
|---|---|---|---|---|
| 1 | Git | `winget install --id Git.Git -e` | `git --version` | 2.4x+ |
| 2 | uv | `winget install --id astral-sh.uv -e` (или `irm https://astral.sh/uv/install.ps1 \| iex`) | `uv --version` | 0.11+ |
| 3 | Python 3.12 (через uv) | `uv python install 3.12` | `uv python find 3.12` | путь к python.exe 3.12.x |
| 4 | Ollama | `winget install --id Ollama.Ollama -e` | `ollama --version`, затем `ollama list` | версия печатается; сервис слушает `http://localhost:11434` |
| 5 | GitHub CLI | `winget install --id GitHub.cli -e`, затем `gh auth login` | `gh auth status` | Logged in to github.com |
| 6 | VS Code | `winget install --id Microsoft.VisualStudioCode -e` | `code --version` | 1.12x |

**Не нужны** (после ADR-015 — демо на Streamlit): Node.js и pnpm, Docker Desktop с WSL2, Supabase CLI. Миграции базы применяет GitHub Actions, офлайн-стенд запускается без Docker. Ставить их стоит, только если захочется поднять свой Kroki в контейнере.

Расширения VS Code ставятся из рекомендаций репозитория (`.vscode/extensions.json`): после открытия папки VS Code предложит их установить.

## Настройки git

```powershell
git config --global core.autocrlf false     # переводы строк задаёт .gitattributes (LF)
git config --global core.longpaths true     # длинные пути node_modules
git config --global init.defaultBranch main
git config --global user.name  "<имя>"
git config --global user.email "<email из GitHub>"
```

Проверка: `git config --global --get core.autocrlf` → `false`.

## SSH-ключ к GitHub

```powershell
ssh-keygen -t ed25519 -C "<email>"            # путь по умолчанию, задайте пароль
Get-Service ssh-agent | Set-Service -StartupType Automatic; Start-Service ssh-agent
ssh-add $env:USERPROFILE\.ssh\id_ed25519
gh ssh-key add $env:USERPROFILE\.ssh\id_ed25519.pub --title "laptop"
ssh -T git@github.com                          # "Hi <login>! You've successfully authenticated"
```

## Консоль и кодировки

- Включите UTF-8: Параметры → Время и язык → Язык → Административные языковые параметры → «Бета-версия: использовать Юникод (UTF-8)». Либо задайте переменную пользователя `PYTHONUTF8=1`. Без этого русские сообщения проверок в `cmd` превращаются в кракозябры.
- Клонируйте репозиторий в короткий путь без пробелов и кириллицы, например `C:\dev\reqgraph`.

## Итоговая проверка

После T-001 должно выполняться:

```powershell
cd C:\dev\reqgraph
uv run python scripts/doctor.py      # таблица OK / FAIL / SKIP
```
