"""Smoke tests for the package skeleton (T-001)."""

import importlib
import re
import socket
from importlib.metadata import version

import pytest
from pytest_socket import SocketConnectBlockedError
import reqgraph
from reqgraph.cli import app
from typer.testing import CliRunner

LAYERS = ["graph", "dsl", "checks", "agents", "llm", "exporters", "sim"]


def test_version_comes_from_package_metadata() -> None:
    assert reqgraph.__version__ == version("reqgraph")
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", reqgraph.__version__)


def test_cli_prints_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"reqgraph {reqgraph.__version__}"


def test_cli_without_arguments_shows_help() -> None:
    result = CliRunner().invoke(app, [])
    assert "Usage" in result.output


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_packages_import(layer: str) -> None:
    module = importlib.import_module(f"reqgraph.{layer}")
    assert module.__doc__


def test_network_is_disabled_in_unit_tests() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(SocketConnectBlockedError):
            sock.connect(("1.1.1.1", 443))
