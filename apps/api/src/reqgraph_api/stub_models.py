"""Stub models for the end-to-end test of the web app (T-504): REQGRAPH_STUB_MODELS=1.

The worker then answers with pydantic-ai test models instead of real providers, as the API tests
do: the interviewer asks numbered questions, the agents return empty drafts. No network, no money.
Only for a local database: with any other DATABASE_URL the worker refuses to start, so a deployed
service can never answer users with stubs."""

import os
import re
from typing import Any
from urllib.parse import urlparse

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

FLAG = "REQGRAPH_STUB_MODELS"
LOCAL = {"127.0.0.1", "localhost", "::1"}
SRS = {
    "purpose": "Онлайн-запись для клиентов.",
    "scope": "Запись и напоминания.",
    "perspective": "Новая система.",
    "glossary": [{"term": "Запись", "definition": "время у мастера"}],
}


def enabled() -> bool:
    return os.environ.get(FLAG, "") in ("1", "true", "yes")


def check_local(database_url: str) -> None:
    host = urlparse(database_url).hostname or ""
    if host not in LOCAL:
        raise RuntimeError(
            f"{FLAG} — только для локальной базы, а DATABASE_URL указывает на {host}"
        )


def _interviewer() -> FunctionModel:
    """Asks «Вопрос N: …» with N from the prompt (ask.md: «Вопрос N из не более чем M»), so runs
    in parallel do not share a counter."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = "".join(str(getattr(part, "content", "")) for m in messages for part in m.parts)
        found = re.search(r"Вопрос (\d+) из", prompt)
        n = found.group(1) if found else "1"
        text = f'{{"text": "Вопрос {n}: как это устроено у вас сейчас?", "area": "scenarios"}}'
        return ModelResponse(parts=[TextPart(text)])

    return FunctionModel(fn)


def models() -> dict[str, Model]:
    stub: dict[str, Any] = {
        "*": TestModel(custom_output_args={"ops": []}),
        "interviewer": _interviewer(),
        "modeler_views": TestModel(custom_output_args={}),
        "standards": TestModel(custom_output_args=SRS),
    }
    return stub
