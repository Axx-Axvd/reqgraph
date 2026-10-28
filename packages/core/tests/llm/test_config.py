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


FAMILIES = {
    "gpt-oss": "openai",
    "nemotron": "nvidia",
    "gemini": "google",
    "gemma": "google",
    "qwen": "alibaba",
    "llama": "meta",
    "glm": "zhipu",
    "deepseek": "deepseek",
    "kimi": "moonshot",
    "minimax": "minimax",
}
AGENT_ROLES = ["*", "interviewer", "analyst", "modeler", "standards", "reviewer"]
EXAMINER_ROLES = ["stakeholder", "judge"]


def family(model: str) -> str:
    for marker, name in FAMILIES.items():
        if marker in model.lower():
            return name
    raise AssertionError(f"неизвестное семейство модели {model}: добавьте в FAMILIES")


@pytest.mark.parametrize("profile", ["free", "cheap"])
def test_simulator_and_judge_are_another_family_than_agents(profile: str) -> None:
    """CLAUDE.md: the simulator and the judge must not share a family with the agents."""
    cfg = load_roles()
    agents = {
        family(s.model)
        for role in AGENT_ROLES
        if role in cfg.profiles[profile]
        for s in cfg.ladder(role, profile)
    }
    for role in EXAMINER_ROLES:
        examiners = {family(s.model) for s in cfg.ladder(role, profile)}
        assert examiners, f"{role} has no models in {profile}"
        assert not examiners & agents, (
            f"{role} shares a family with agents in {profile}: {examiners & agents}"
        )


def test_long_context_role_starts_on_a_provider_without_a_tight_limit() -> None:
    """The analyst reads the whole interview, so its first model must not be a small-context one."""
    cfg = load_roles()
    first = cfg.ladder("analyst", "free")[0]
    assert cfg.providers[first.provider].max_input_tokens is None


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "roles.yaml"
    bad.write_text(
        "providers:\n  groq: {base_url: 'https://x', key_env: GROQ_API_KEY}\n"
        "profiles:\n  free: {'*': [nosuch/model]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="nosuch"):
        load_roles(bad)


def test_unknown_profile_and_role_are_errors(tmp_path: Path) -> None:
    cfg = load_roles()
    with pytest.raises(ConfigError, match="профил"):
        cfg.ladder("analyst", "premium")
    no_wildcard = tmp_path / "roles.yaml"
    no_wildcard.write_text(
        "providers:\n  groq: {base_url: 'https://x', key_env: GROQ_API_KEY}\n"
        "profiles:\n  free: {analyst: [groq/m]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="рол"):
        load_roles(no_wildcard).ladder("nobody", "free")


def test_profile_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQGRAPH_PROFILE", "local")
    cfg = load_roles()
    assert cfg.ladder("analyst")[0].provider == "ollama"


def test_the_simulated_client_has_its_own_temperature(tmp_path: Path) -> None:
    cfg = load_roles()
    assert cfg.temperature("stakeholder") == 0.7  # 03_agents: the client talks like a person
    assert cfg.temperature("analyst") == cfg.defaults.temperature
    bad = tmp_path / "roles.yaml"
    from reqgraph.llm.config import ROLES_YAML

    text = ROLES_YAML.read_text(encoding="utf-8")
    bad.write_text(text.replace("temperature: 0.7", "temperature: 5"), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_roles(bad)


@pytest.mark.parametrize("profile", ["free", "cheap", "local"])
def test_every_profile_has_an_embedding_model(profile: str) -> None:
    step = load_roles().embedding(profile)
    assert step.provider in load_roles().providers
    with pytest.raises(ConfigError, match="эмбеддингов"):
        load_roles().embedding("nope")
