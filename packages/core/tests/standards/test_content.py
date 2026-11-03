"""SRS sections built by code (T-408): features, NFR by characteristic, interfaces, issues."""

from pathlib import Path

from reqgraph.graph import ArtifactGraph, GraphPatch
from reqgraph.graph.store import FileStore
from reqgraph.standards import Section, load_structure
from reqgraph.standards.content import code_content

GARAGE61 = Path(__file__).resolve().parents[4] / "examples" / "garage61"
STRUCTURE = load_structure("iso29148_srs")


def graph() -> ArtifactGraph:
    return FileStore(GARAGE61).load().graph


def section(section_id: str) -> Section:
    return next(s for s in STRUCTURE.sections if s.id == section_id)


def text(section_id: str, g: ArtifactGraph | None = None) -> tuple[str, list[str]]:
    built = code_content(section(section_id), g or graph())
    assert built is not None
    return built


def test_the_structure_follows_wiegers_with_originals() -> None:
    titles = [s.title_en for s in STRUCTURE.sections]
    assert titles[:2] == ["Introduction", "Purpose"]
    assert "System features" in titles and "Appendix C: Issues list" in titles
    assert all(s.title_en for s in STRUCTURE.sections)
    llm_required = {s.llm_field for s in STRUCTURE.required if s.llm_field}
    assert llm_required == {"purpose", "scope", "perspective", "glossary"}
    assert [s.number for s in STRUCTURE.sections][-5:] == ["", "", "", "", ""]  # appendices


def test_a_feature_is_a_user_requirement_with_its_scenario_and_frs() -> None:
    body, refs = text("SEC-SRS-3")
    assert "### 3.1 Онлайн-запись частного клиента (UR-001)" in body
    first = body.split("### 3.2")[0]
    assert (
        "**Описание и приоритет.**" in first
        and "**Последовательность «стимул — отклик».**" in first
    )
    assert "- FR-001 Каталог услуг:" in first and "FR-006" not in first  # FR-006 refines UR-004
    assert "UR-001" in refs and "FR-001" in refs


def test_frs_without_a_user_requirement_go_to_other_features() -> None:
    g = graph()
    op = {
        "op": "add",
        "kind": "FR",
        "tmp_id": "f",
        "fields": {"title": "Отчёт", "statement": "Система должна строить отчёт по выручке."},
    }
    g = g.apply(GraphPatch.model_validate({"ops": [op]}), actor="user").graph
    body, _ = text("SEC-SRS-3", g)
    assert "Прочие функции" in body and "Отчёт: Система должна строить отчёт" in body


def test_nfrs_are_split_by_their_iso_25010_characteristic() -> None:
    g = graph()
    sections = ("SEC-SRS-5.1", "SEC-SRS-5.2", "SEC-SRS-5.3", "SEC-SRS-5.4")
    found = [set(text(s, g)[1]) for s in sections]
    every = {n.id for n in g.nodes_of("NFR")}
    assert set().union(*found) == every  # each NFR lands somewhere
    assert sum(len(f) for f in found) == len(every)  # and only once


def test_software_interfaces_are_integrations_and_external_systems() -> None:
    _body, refs = text("SEC-SRS-4.2")
    assert any(r.startswith("C4-EXT") for r in refs)


def test_issues_list_conflicts_and_assumptions() -> None:
    g = graph()
    ops = [
        {"op": "link", "from": "FR-007", "rel": "conflicts_with", "to": "FR-008"},
        {"op": "update", "id": "FR-012", "fields": {"assumption": True}},
    ]
    g = g.apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    body, _refs = text("SEC-SRS-C", g)
    assert "FR-007 ↔ FR-008" in body and "FR-012" in body
    assert body.count("FR-007 ↔") + body.count("FR-008 ↔") == 1  # a symmetric pair once
    empty, _ = text("SEC-SRS-C")
    assert empty == ""


def test_models_list_entities_with_fields_and_processes() -> None:
    _body, refs = text("SEC-SRS-B")
    assert "ENT-01" in refs and "PRC-01" in refs


def test_trace_is_a_table() -> None:
    body, _refs = text("SEC-SRS-E")
    assert (
        body.startswith("| ФТ |")
        and "| FR-006 Расписание мастеров | UR-004 | BR-001, BR-002 |" in body
    )


TZ = load_structure("gost34_602")


def tz(section_id: str) -> Section:
    return next(s for s in TZ.sections if s.id == section_id)


def test_the_tz_has_every_section_of_gost_34_602() -> None:
    numbers = [s.number for s in TZ.sections if s.number]
    assert [n for n in numbers if "." not in n] == [str(i) for i in range(1, 11)]
    assert [n for n in numbers if n.startswith("4.1.")] == [f"4.1.{i}" for i in range(1, 15)]
    assert [n for n in numbers if n.startswith("4.3.")] == [f"4.3.{i}" for i in range(1, 9)]
    assert {s.id for s in TZ.required} >= {"SEC-TZ-1.1", "SEC-TZ-2.1", "SEC-TZ-4.2", "SEC-TZ-7"}


def test_constraints_are_split_by_topic() -> None:
    from reqgraph.standards.content import section_text

    g = graph()
    deadline = section_text(tz("SEC-TZ-1.4"), g)[1]
    budget = section_text(tz("SEC-TZ-1.5"), g)[1]
    law = section_text(tz("SEC-TZ-4.1.9"), g)[1]
    assert deadline == ["CON-003"] and budget == ["CON-002"] and "CON-001" in law


def test_fixed_texts_project_and_language() -> None:
    from reqgraph.standards.content import CONTRACT, NOT_APPLICABLE, section_text

    g = graph()
    assert section_text(tz("SEC-TZ-1.2"), g)[0] == CONTRACT
    assert section_text(tz("SEC-TZ-4.1.7"), g)[0] == NOT_APPLICABLE
    named = section_text(tz("SEC-TZ-1.1"), g, project_name="Гараж 61", project_id="garage61")
    assert "Гараж 61" in named[0] and "garage61" in named[0]
    assert "русском" in section_text(tz("SEC-TZ-4.3.3"), g, langs=["ru"])[0]
    assert "Бриф заказчика" in section_text(tz("SEC-TZ-10"), g)[0]


def test_llm_text_of_the_tz_comes_from_the_srs_sections() -> None:
    from reqgraph.standards.content import llm_texts, section_text

    g = graph()
    ops = [
        {
            "op": "add",
            "kind": "SEC",
            "tmp_id": f"s{i}",
            "fields": {"id": sid, "template": "iso29148_srs", "text": text},
        }
        for i, (sid, text) in enumerate(
            [
                ("SEC-SRS-1.1", "Запись в сервис."),
                ("SEC-SRS-2.4", "Браузер."),
                ("SEC-SRS-4.3", "Принтер чеков."),
            ]
        )
    ]
    g = g.apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    texts = llm_texts(g)
    assert texts["purpose"] == "Запись в сервис."
    assert section_text(tz("SEC-TZ-2.1"), g, texts)[0] == "Запись в сервис."
    both = section_text(tz("SEC-TZ-4.3.5"), g, texts)[0]  # environment + hardware
    assert both == "Браузер.\n\nПринтер чеков."
    assert section_text(tz("SEC-TZ-2.1"), g)[0] == ""  # no Standards text yet


def test_structure_of_the_system_is_the_c4_model() -> None:
    from reqgraph.standards.content import section_text

    _text, refs = section_text(tz("SEC-TZ-4.1.1"), graph())
    assert refs and all(r.startswith("C4-") for r in refs) and "C4-EXT" not in " ".join(refs)


PROGRAM = load_structure("gost19_201")


def program(section_id: str) -> Section:
    return next(s for s in PROGRAM.sections if s.id == section_id)


def test_the_program_tz_has_every_section_of_gost_19_201() -> None:
    numbers = [s.number for s in PROGRAM.sections if s.number]
    assert [n for n in numbers if "." not in n] == [str(i) for i in range(1, 9)]
    assert [n for n in numbers if n.startswith("4.")] == [f"4.{i}" for i in range(1, 9)]
    assert [s.title for s in PROGRAM.sections if not s.number] == [
        "Приложение А. Модели программы",
        "Приложение Б. Трассировка требований",
    ]
    required = {s.id.removeprefix("SEC-TZ19-") for s in PROGRAM.required}
    assert required == {"1.1", "1.2", "3.1", "4.1", "8"}


def test_every_nfr_of_the_program_tz_lands_once() -> None:
    from reqgraph.standards.content import section_text

    g = graph()
    placed = [r for s in PROGRAM.sections for r in section_text(s, g)[1] if r.startswith("NFR-")]
    assert sorted(placed) == sorted(n.id for n in g.nodes_of("NFR"))


def test_compatibility_joins_interfaces_nfr_and_technology() -> None:
    from reqgraph.standards.content import CONTRACT, section_text

    _text, refs = section_text(program("SEC-TZ19-4.5"), graph())
    assert any(r.startswith("C4-EXT") for r in refs)
    _special, found = section_text(program("SEC-TZ19-4.8"), graph())
    assert "CON-001" in found and any(r.startswith("NFR-") for r in found)
    stages, _ = section_text(program("SEC-TZ19-7"), graph())
    assert "CON-003" in stages and stages.endswith(CONTRACT)


def test_a_constraint_goes_to_the_sections_of_its_type_not_of_its_words() -> None:
    """T-314: «в России» has no word of law, «на серверах» has a word of technology — both are
    legal by their type and land in the information security section only."""
    from reqgraph.standards.content import section_text

    ops = [
        {
            "op": "add",
            "kind": "CON",
            "tmp_id": f"c{i}",
            "fields": {"title": title, "type": "legal", "statement": statement},
        }
        for i, (title, statement) in enumerate(
            [
                ("Данные в РФ", "Данные клиентов хранятся в России."),
                ("Хранение у заказчика", "Данные читателей хранятся на серверах университета."),
            ]
        )
    ]
    g = graph().apply(GraphPatch.model_validate({"ops": ops}), actor="user").graph
    new = sorted(set(g.nodes) - set(graph().nodes))
    law = section_text(tz("SEC-TZ-4.1.9"), g)[1]
    tech = section_text(tz("SEC-TZ-4.1.13"), g)[1] + section_text(tz("SEC-TZ-4.3.4"), g)[1]
    assert set(new) <= set(law) and not set(new) & set(tech)
