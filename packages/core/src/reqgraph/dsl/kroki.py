"""SVG of diagrams through Kroki (ADR-010): DBML, PlantUML, Structurizr and BPMN.

Kroki also says whether a diagram compiles (checks SCH-004/005): a syntax error comes back as
HTTP 400 with the reason and the line. Without network the result is `offline` — checks report
it as skipped (info), not as an error. SVGs are cached on disk by a hash of kind + text.
`KROKI_URL` points to kroki.io or to an own container (offline stand, T-507).
"""

import asyncio
import hashlib
import html
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

DEFAULT_URL = "https://kroki.io"
TIMEOUT_S = 20.0
KIND_BY_SUFFIX = {".dbml": "dbml", ".puml": "plantuml", ".dsl": "structurizr", ".bpmn": "bpmn"}
KINDS = frozenset(KIND_BY_SUFFIX.values())


@dataclass(frozen=True)
class RenderResult:
    svg: str | None = None
    error: str | None = None  # the diagram does not compile: Kroki's message with the line
    offline: bool = False  # Kroki could not be reached: not the diagram's fault
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.svg is not None


def kroki_url() -> str:
    return os.environ.get("KROKI_URL", DEFAULT_URL).rstrip("/")


def cache_dir() -> Path:
    """REQGRAPH_CACHE_DIR, else the user cache folder (%LOCALAPPDATA% on Windows)."""
    if "REQGRAPH_CACHE_DIR" in os.environ:
        return Path(os.environ["REQGRAPH_CACHE_DIR"]) / "kroki"
    if sys.platform == "win32" and "LOCALAPPDATA" in os.environ:
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "reqgraph" / "kroki"


def _plain(body: str) -> str:
    """Kroki may draw the error as an SVG picture: keep only its text."""
    if body.lstrip().startswith(("<?xml", "<svg")):
        body = " ".join(html.unescape(t) for t in re.findall(r">([^<>]+)<", body) if t.strip())
    return " ".join(body.split())


def _post(url: str, source: str) -> RenderResult:
    request = urllib.request.Request(
        url,
        data=source.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "text/plain; charset=utf-8",  # no Accept: errors then come as text
            "User-Agent": f"reqgraph/{version('reqgraph')}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return RenderResult(svg=response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _plain(exc.read().decode("utf-8", errors="replace"))
        if 400 <= exc.code < 500:
            return RenderResult(error=body or f"HTTP {exc.code}")
        return RenderResult(offline=True, error=f"Kroki: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return RenderResult(offline=True, error=f"Kroki недоступен ({url}): {exc}")


async def render_svg(kind: str, source: str) -> RenderResult:
    """SVG of a diagram; `kind` is dbml, plantuml, structurizr or bpmn."""
    if kind not in KINDS:
        raise ValueError(f"Kroki: вид диаграммы «{kind}» не поддерживается, есть {sorted(KINDS)}")
    digest = hashlib.sha256(f"{kind}\n{source}".encode()).hexdigest()
    cached = cache_dir() / kind / f"{digest}.svg"
    if cached.is_file():
        return RenderResult(svg=cached.read_bytes().decode("utf-8"), cached=True)
    result = await asyncio.to_thread(_post, f"{kroki_url()}/{kind}/svg", source)
    if result.svg is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(result.svg.encode("utf-8"))
    return result
