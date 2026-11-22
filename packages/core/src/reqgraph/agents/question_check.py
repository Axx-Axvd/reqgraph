"""T-320 · the interviewer's question is checked by code before the client sees it: no jargon
above the client's IT level unless explained next to it (the T-316 dictionary), and one question,
not several. The problems go back to the model once, in Russian, as what to fix."""

from reqgraph.checks.jargon import explained_terms, unknown_terms

SPECIALIST = 3  # understands every term of the dictionary


def unclear_terms(question: str, level: int) -> list[str]:
    """Terms of the question the client at this level does not understand, unexplained."""
    if level >= SPECIALIST:
        return []
    unknown = unknown_terms(question, level)
    explained = explained_terms(question, unknown)
    return [term for term in unknown if term not in explained]


def check_question(question: str, level: int) -> list[str]:
    issues = []
    terms = unclear_terms(question, level)
    if terms:
        issues.append(
            f"слова, непонятные заказчику: {', '.join(terms)} — скажи обычными словами "
            "или поясни примером сразу после слова"
        )
    if question.count("?") > 1:
        issues.append("несколько вопросов в одном: оставь один вопрос")
    return issues
