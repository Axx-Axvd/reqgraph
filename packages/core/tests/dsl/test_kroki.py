"""SVG through Kroki: cassettes (no network in tests), errors with line numbers, offline, cache.

Re-record (network needed):
  uv run pytest packages/core/tests/dsl/test_kroki.py --record-mode=rewrite --force-enable-socket
"""

import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from reqgraph.dsl.kroki import KIND_BY_SUFFIX, RenderResult, cache_dir, render_svg

from .conftest import GARAGE61, GOLDEN

MODELS = GARAGE61.parent
SOURCES = {
    "dbml": MODELS / "data" / "erd.dbml",
    "plantuml": MODELS / "uml" / "use_cases.puml",
    "structurizr": MODELS / "c4" / "workspace.dsl",
    "bpmn": GOLDEN / "PRC-01_booking.bpmn",
}


@pytest.fixture(autouse=True)
def private_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "cache"
    monkeypatch.setenv("REQGRAPH_CACHE_DIR", str(cache))
    monkeypatch.setenv("KROKI_URL", "https://kroki.io")
    return cache


def render(kind: str, source: str) -> RenderResult:
    return asyncio.run(render_svg(kind, source))


@pytest.mark.vcr
@pytest.mark.parametrize("kind", sorted(SOURCES))
def test_reference_models_render_to_svg(kind: str) -> None:
    result = render(kind, SOURCES[kind].read_text(encoding="utf-8"))
    assert result.ok and result.svg is not None and "<svg" in result.svg


@pytest.mark.vcr
def test_plantuml_error_has_the_line() -> None:
    result = render("plantuml", '@startuml\nusecase "A" as UC01\nUC01 -->\n@enduml\n')
    assert not result.ok and not result.offline
    assert result.error is not None and "line: 2" in result.error


@pytest.mark.vcr
def test_structurizr_error_names_the_element() -> None:
    result = render("structurizr", 'workspace {\n model {\n a = person "A"\n a -> b "x"\n }\n}\n')
    assert result.error is not None and '"b"' in result.error


def test_offline_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KROKI_URL", "http://127.0.0.1:9")  # nothing listens there
    result = render("plantuml", "@startuml\nA -> B\n@enduml\n")
    assert result.offline and not result.ok and result.svg is None


@pytest.mark.vcr
def test_second_render_comes_from_the_cache(
    private_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = SOURCES["plantuml"].read_text(encoding="utf-8")
    first = render("plantuml", source)
    monkeypatch.setenv("KROKI_URL", "http://127.0.0.1:9")  # would be offline without the cache
    second = render("plantuml", source)
    assert first.ok and not first.cached
    assert second.cached and second.svg == first.svg
    assert len(list(private_cache.rglob("*.svg"))) == 1


def test_errors_are_not_cached(private_cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KROKI_URL", "http://127.0.0.1:9")
    render("plantuml", "@startuml\nA -> B\n@enduml\n")
    assert not list(private_cache.rglob("*"))


def test_error_drawn_as_svg_is_turned_into_text() -> None:
    from reqgraph.dsl.kroki import _plain

    svg = '<?xml version="1.0"?><svg><text><tspan>Error 400: a -&gt; b</tspan></text></svg>'
    assert _plain(svg) == "Error 400: a -> b"
    assert _plain("Error 400:  line\n2") == "Error 400: line 2"


def test_unknown_kind() -> None:
    with pytest.raises(ValueError, match="mermaid"):
        render("mermaid", "graph TD")


def test_kind_by_file_suffix() -> None:
    assert KIND_BY_SUFFIX == {
        ".dbml": "dbml",
        ".puml": "plantuml",
        ".dsl": "structurizr",
        ".bpmn": "bpmn",
    }


def test_server_error_of_kroki_counts_as_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 5xx is Kroki's trouble, not the diagram's: skipped, not an error of the model."""

    class Unavailable(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(503)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Unavailable)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    monkeypatch.setenv("KROKI_URL", f"http://127.0.0.1:{server.server_port}")
    result = render("plantuml", "@startuml\nA -> B\n@enduml\n")
    thread.join(5)
    server.server_close()
    assert result.offline and result.error is not None and "503" in result.error


def test_default_cache_folders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("REQGRAPH_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(sys, "platform", "linux")
    assert cache_dir() == tmp_path / "xdg" / "reqgraph" / "kroki"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert cache_dir() == tmp_path / "local" / "reqgraph" / "kroki"
