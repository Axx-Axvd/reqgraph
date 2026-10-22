"""Check that the development environment is ready for reqgraph.

Prints a table OK / FAIL / SKIP with a hint for every failed item. Uses only the standard
library, so it runs before `uv sync`:

    uv run python scripts/doctor.py           # tools, Docker, Ollama, Kroki, model providers
    uv run python scripts/doctor.py --chat    # plus one tiny free completion per provider

API keys are read from the environment or from .env in the repository root. When a key is
missing, a placeholder is sent: in cloud sessions the egress proxy injects the real key
(network secrets). Key values are never printed; only the HTTP status is shown.
Exit code: 1 if any required check failed, else 0.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "placeholder"
TIMEOUT_S = 20


@dataclass
class Row:
    group: str
    name: str
    status: str  # OK | FAIL | SKIP
    detail: str
    hint: str = ""


@dataclass
class Provider:
    name: str
    key_env: str
    auth_url: str  # GET endpoint that requires a valid key
    chat_url: str
    chat_model: str
    required: bool
    signup: str


PROVIDERS = [
    Provider(
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1/key",
        "https://openrouter.ai/api/v1/chat/completions",
        "openrouter/free",
        True,
        "https://openrouter.ai/settings/keys",
    ),
    Provider(
        "Groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1/models",
        "https://api.groq.com/openai/v1/chat/completions",
        "openai/gpt-oss-20b",
        True,
        "https://console.groq.com/keys",
    ),
    Provider(
        "Google AI Studio",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "gemini-3.5-flash-lite",
        False,
        "https://aistudio.google.com/apikey",
    ),
]

# (command, minimum major version or 0, required, hint)
TOOLS: list[tuple[str, int, bool, str]] = [
    ("git", 0, True, "Windows: winget install --id Git.Git -e"),
    ("uv", 0, True, "Windows: winget install --id astral-sh.uv -e"),
    ("node", 22, True, "Windows: winget install --id OpenJS.NodeJS.LTS -e"),
    ("pnpm", 0, True, "corepack enable && corepack prepare pnpm@latest --activate"),
    ("docker", 0, False, "Windows: winget install --id Docker.DockerDesktop -e (WSL2)"),
    ("supabase", 0, False, "нужен с T-004: pnpm dlx supabase --version или scoop install supabase"),
    ("gh", 0, False, "Windows: winget install --id GitHub.cli -e"),
    ("ollama", 0, False, "Windows: winget install --id Ollama.Ollama -e (офлайн-профиль)"),
]


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines; never overrides variables already set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def run(cmd: list[str], timeout: int = TIMEOUT_S) -> tuple[int, str]:
    exe = shutil.which(cmd[0])
    if exe is None:
        return 127, "не найден в PATH"
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"таймаут {timeout} с"
    text = proc.stdout if proc.returncode == 0 else (proc.stderr or proc.stdout)
    out = text.strip().splitlines()
    return proc.returncode, out[0] if out else ""


def http(
    method: str, url: str, key: str | None = None, body: dict[str, object] | None = None
) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "reqgraph-doctor")
    if key is not None:
        req.add_header("Authorization", f"Bearer {key}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(512).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        return 0, str(reason)[:80]


def check_python() -> Row:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 12)
    return Row(
        "tools",
        "python",
        "OK" if ok else "FAIL",
        platform.python_version(),
        "" if ok else "uv python install 3.12 и запуск через uv run",
    )


def check_tools() -> list[Row]:
    rows = [check_python()]
    for cmd, minimum, required, hint in TOOLS:
        code, out = run([cmd, "--version"])
        if code == 0:
            major = re.search(r"(\d+)\.", out)
            too_old = bool(minimum) and (major is None or int(major.group(1)) < minimum)
            hint_old = f"нужна версия >= {minimum}" if too_old else ""
            rows.append(Row("tools", cmd, "FAIL" if too_old else "OK", out[:60], hint_old))
        else:
            rows.append(Row("tools", cmd, "FAIL" if required else "SKIP", out[:60], hint))
    return rows


def check_docker() -> Row:
    if shutil.which("docker") is None:
        return Row(
            "services",
            "docker daemon",
            "SKIP",
            "docker не установлен",
            "нужен для T-004 и офлайн-стенда",
        )
    code, out = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if code == 0:
        return Row("services", "docker daemon", "OK", f"server {out}")
    return Row(
        "services",
        "docker daemon",
        "FAIL",
        out[:60],
        "запустите Docker Desktop (Linux: sudo dockerd &)",
    )


def check_ollama() -> Row:
    base = (
        os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        .rstrip("/")
        .removesuffix("/v1")
    )
    code, body = http("GET", f"{base}/api/version")
    if code == 200:
        return Row("services", "ollama", "OK", body.strip()[:60])
    return Row(
        "services",
        "ollama",
        "SKIP",
        f"{base} недоступен",
        "нужен только для профиля local: ollama serve",
    )


def check_kroki() -> Row:
    url = os.environ.get("KROKI_URL", "https://kroki.io").rstrip("/")
    req = urllib.request.Request(
        f"{url}/plantuml/svg", data=b"@startuml\nA -> B\n@enduml", method="POST"
    )
    req.add_header("Content-Type", "text/plain")
    req.add_header("User-Agent", "reqgraph-doctor")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            ok = resp.status == 200 and b"<svg" in resp.read(2048)
            return Row("services", "kroki", "OK" if ok else "FAIL", f"{url} -> {resp.status}")
    except urllib.error.HTTPError as e:
        return Row(
            "services",
            "kroki",
            "FAIL",
            f"{url} -> {e.code}",
            "офлайн SCH-004/005 пропускаются с info",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return Row(
            "services",
            "kroki",
            "FAIL",
            str(getattr(e, "reason", e))[:60],
            "проверьте сеть или KROKI_URL",
        )


def check_provider(p: Provider, chat: bool) -> list[Row]:
    key = os.environ.get(p.key_env)
    source = "ключ из env/.env" if key else "плейсхолдер (network secret)"
    code, body = http("GET", p.auth_url, key or PLACEHOLDER)
    if code == 200:
        detail = f"HTTP 200, {source}"
        if p.name == "OpenRouter":
            try:
                daily = json.loads(body)["data"].get("free_model_daily_requests") or {}
                detail += f", free RPD {daily.get('remaining')}/{daily.get('limit')}"
            except (ValueError, KeyError, TypeError):
                pass
        rows = [Row("providers", p.name, "OK", detail)]
    else:
        status = "FAIL" if p.required or key else "SKIP"
        hint = (
            "хост недоступен: добавьте его в Allowed domains окружения"
            if code in (0, 403) and "tunnel" in body.lower()
            else f"задайте {p.key_env} в .env (ключ: {p.signup})"
        )
        return [Row("providers", p.name, status, f"HTTP {code}, {source}", hint)]

    if chat:
        payload = {
            "model": p.chat_model,
            "messages": [{"role": "user", "content": "Reply: ok"}],
            "max_tokens": 5,
        }
        ccode, cbody = http("POST", p.chat_url, key or PLACEHOLDER, payload)
        if ccode == 200:
            rows.append(Row("providers", f"{p.name} chat", "OK", f"{p.chat_model}, HTTP 200"))
        else:
            msg = cbody.replace("\n", " ")[:50]
            rows.append(
                Row(
                    "providers",
                    f"{p.name} chat",
                    "FAIL",
                    f"{p.chat_model}, HTTP {ccode}",
                    f"модель или лимит: {msg}",
                )
            )
    return rows


def print_table(rows: list[Row]) -> None:
    widths = [max(len(getattr(r, f)) for r in rows) for f in ("group", "name", "status")]
    for r in rows:
        line = f"{r.group:<{widths[0]}}  {r.name:<{widths[1]}}  {r.status:<{widths[2]}}  {r.detail}"
        print(line)
        if r.status != "OK" and r.hint:
            print(" " * (widths[0] + widths[1] + widths[2] + 6) + f"-> {r.hint}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--chat", action="store_true", help="also send one tiny completion per provider"
    )
    ap.add_argument("--offline", action="store_true", help="skip network checks")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv(ROOT / ".env")
    rows = [*check_tools(), check_docker(), check_ollama()]
    if not args.offline:
        rows.append(check_kroki())
        for p in PROVIDERS:
            rows += check_provider(p, args.chat)

    print(f"reqgraph doctor · {platform.system()} {platform.release()} · {ROOT}")
    print_table(rows)
    counts = {s: sum(r.status == s for r in rows) for s in ("OK", "FAIL", "SKIP")}
    print(f"\nOK {counts['OK']} · FAIL {counts['FAIL']} · SKIP {counts['SKIP']}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
