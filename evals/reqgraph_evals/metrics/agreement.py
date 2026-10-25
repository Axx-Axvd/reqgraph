"""Agreement of the judge with a person (09_eval, R4): Cohen's kappa and plain agreement.

Kappa corrects the share of equal answers for the agreement two raters would reach by chance
(preflight, item 27: the backlog said «agreement >= 0.8» without the measure). Binary labels.
"""

from collections.abc import Sequence


def agreement(a: Sequence[bool], b: Sequence[bool]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("нужны две непустые разметки одной длины")
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    observed = agreement(a, b)
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1:
        return 1.0  # both raters gave one and the same answer to every pair
    return (observed - expected) / (1 - expected)
