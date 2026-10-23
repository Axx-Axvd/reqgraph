"""Registry of checks: a new check is a class with @register in a module of checks/catalog.py."""

import re

from reqgraph.checks.base import CHECK_ID, BaseCheck

_ID = re.compile(CHECK_ID)


class Registry:
    def __init__(self) -> None:
        self._checks: dict[str, BaseCheck] = {}

    def register[C: type[BaseCheck]](self, cls: C) -> C:
        """Decorator: creates one instance of the check; ids must be valid and unique."""
        check = cls()
        if not _ID.fullmatch(check.id):
            raise ValueError(
                f"{cls.__name__}: id «{check.id}» не по шаблону SCH|SND|ISO|TRC|TPL-NNN"
            )
        if check.id in self._checks:
            raise ValueError(f"проверка {check.id} уже зарегистрирована")
        self._checks[check.id] = check
        return cls

    def checks(self) -> list[BaseCheck]:
        return [self._checks[i] for i in sorted(self._checks)]


REGISTRY = Registry()
register = REGISTRY.register


def all_checks() -> list[BaseCheck]:
    """Every real check, sorted by id (modules are imported by checks/catalog.py)."""
    import reqgraph.checks.catalog  # noqa: F401 - registers the checks on import

    return REGISTRY.checks()
