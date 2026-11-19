"""Stub models of the web e2e test (T-504): never against a remote database."""

import pytest
from reqgraph_api import stub_models

pytestmark = pytest.mark.anyio


def test_stub_models_refuse_a_remote_database() -> None:
    stub_models.check_local("postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    stub_models.check_local("postgresql://postgres@localhost/postgres")
    with pytest.raises(RuntimeError, match="только для локальной базы"):
        stub_models.check_local("postgresql://u:p@aws-0-eu.pooler.supabase.com:5432/postgres")


def test_the_flag_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(stub_models.FLAG, raising=False)
    assert not stub_models.enabled()
    monkeypatch.setenv(stub_models.FLAG, "1")
    assert stub_models.enabled()
    assert {"*", "interviewer", "standards"} <= set(stub_models.models())


async def test_the_stub_interviewer_numbers_its_question_from_the_prompt() -> None:
    from pydantic_ai import Agent
    from reqgraph.agents.nodes import Question

    agent = Agent(stub_models.models()["interviewer"], output_type=Question)
    out = await agent.run("…\nВопрос 3 из не более чем 40.\n…")
    assert out.output.text.startswith("Вопрос 3:")
