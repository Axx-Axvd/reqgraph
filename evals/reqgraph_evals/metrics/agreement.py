"""Agreement of the judge with a person (09_eval, R4): Cohen's kappa and plain agreement.

Kappa corrects the share of equal answers for the agreement two raters would reach by chance
(preflight, item 27: the backlog said «agreement >= 0.8» without the measure). Any labels that
compare by equality: yes / no, or the judge's three levels (full / partial / none).
"""

from collections import Counter
from collections.abc import Hashable, Sequence


def agreement(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("нужны две непустые разметки одной длины")
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float:
    observed = agreement(a, b)
    ca, cb, n = Counter(a), Counter(b), len(a)
    expected = sum(ca[label] * cb[label] for label in ca) / (n * n)
    if expected == 1:
        return 1.0  # both raters gave one and the same answer to every item
    return (observed - expected) / (1 - expected)
