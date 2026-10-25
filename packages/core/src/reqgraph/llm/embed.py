"""Embeddings through llm/ (ADR-013): pydantic-ai's Embedder on an OpenAI-compatible endpoint.

Used by the recall metric (T-304) to find candidate matches between found and hidden requirements
before the judge decides. Vectors are cached on disk by model and text: the same reference is
embedded once, not on every run (free-tier limits). Keys never reach the cache or the log.
"""

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

from pydantic_ai.embeddings import Embedder, EmbeddingModel
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.providers.openai import OpenAIProvider

from reqgraph.llm.config import load_roles
from reqgraph.llm.router import api_key, base_url


def cache_dir() -> Path:
    root = os.environ.get("REQGRAPH_CACHE_DIR")
    return (Path(root) if root else Path.home() / ".cache" / "reqgraph") / "embeddings"


def embedding_model(profile: str | None = None) -> tuple[EmbeddingModel, str]:
    """The profile's embedding model and its id ("provider/model")."""
    cfg = load_roles()
    step = cfg.embedding(profile)
    provider = cfg.providers[step.provider]
    client = OpenAIProvider(base_url=base_url(provider), api_key=api_key(provider))
    return OpenAIEmbeddingModel(step.model, provider=client), step.id


async def embed(
    texts: Sequence[str],
    *,
    profile: str | None = None,
    model: EmbeddingModel | None = None,
    model_id: str | None = None,
    cache: Path | None = None,
) -> list[list[float]]:
    """One vector per text, in order; cached ones are not asked for again."""
    if model is None:
        model, model_id = embedding_model(profile)
    key_model = model_id or model.model_name
    folder = (cache or cache_dir()) / key_model.replace("/", "_")
    keys = [hashlib.sha256(f"{key_model}\n{t}".encode()).hexdigest() for t in texts]
    vectors: dict[str, list[float]] = {}
    for key in set(keys):
        path = folder / f"{key}.json"
        if path.is_file():
            vectors[key] = json.loads(path.read_text(encoding="utf-8"))
    missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in vectors]
    unique = list(dict(missing).items())
    if unique:
        result = await Embedder(model).embed_documents([t for _, t in unique])
        folder.mkdir(parents=True, exist_ok=True)
        for (key, _), vector in zip(unique, result.embeddings, strict=True):
            vectors[key] = [float(x) for x in vector]
            (folder / f"{key}.json").write_text(json.dumps(vectors[key]), encoding="utf-8")
    return [vectors[k] for k in keys]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
    return dot / norm if norm else 0.0
