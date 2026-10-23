"""roles.yaml loading and validation (T-005)."""

from pathlib import Path

import pytest
from reqgraph.llm.config import ConfigError, load_roles

ROLES = ["interviewer", "analyst", "modeler", "standards", "reviewer", "stakeholder", "judge"]


def test_bundled_roles_yaml_loads() -> None:
    cfg = load_roles()
    assert set(cfg.profiles) == {"free", "cheap", "local"}
    assert cfg.defaults.retries >= 1
    assert cfg.budget.run_usd > 0


@pytest.mark.parametrize("profile", ["free", "cheap", "local"])
@pytest.mark.parametrize("role", ROLES)
def test_every_role_resolves_in_every_profile(profile: str, role: str) -> None:
    steps = load_roles().ladder(role, profile)
    assert steps, f"{role} has no models in {profile}"
    for step in steps:
        assert step.provider in load_roles().providers


def test_role_falls_back_to_wildcard() -> None:
    cfg = load_roles()
    assert cfg.ladder("analyst", "local") == cfg.ladder("*", "local")


def test_free_models_are_marked_free() -> None:
    cfg = load_roles()
    for step in cfg.ladder("analyst", "free"):
        assert cfg.is_free(step)  # OpenRouter ":free" ids
    assert cfg.is_free(cfg.ladder("reviewer", "free")[0])  # Groq is a free tier
    assert not cfg.is_free(cfg.ladder("analyst", "cheap")[0])  # DeepSeek is paid


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "roles.yaml"
    bad.write_text(
        "providers:\n  groq: {base_url: 'https://x', key_env: GROQ_API_KEY}\n"
        "profiles:\n  free: {'*': [nosuch/model]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="nosuch"):
        load_roles(bad)


def test_unknown_profile_and_role_are_errors() -> None:
    cfg = load_roles()
    with pytest.raises(ConfigError, match="профил"):
        cfg.ladder("analyst", "premium")
    with pytest.raises(ConfigError, match="рол"):
        cfg.ladder("nobody", "free")


def test_profile_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQGRAPH_PROFILE", "local")
    cfg = load_roles()
    assert cfg.ladder("analyst")[0].provider == "ollama"
