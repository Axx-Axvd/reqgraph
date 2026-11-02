"""Use case diagrams and C4 workspaces read and built by code (T-207): what the Modeler writes and
the hand-written files of garage61 in the same conventions (REVIEW.md, No. 3)."""

from reqgraph.dsl.c4 import C4Model, Element, Relationship, parse_workspace, render_workspace
from reqgraph.dsl.plantuml import UseCase, UseCaseModel, parse_use_cases, render_use_cases
from reqgraph.graph.store.scan import scan_c4, scan_puml

from .conftest import GARAGE61

MODELS = GARAGE61.parent
PUML = (MODELS / "uml" / "use_cases.puml").read_text(encoding="utf-8")
DSL = (MODELS / "c4" / "workspace.dsl").read_text(encoding="utf-8")


def test_garage61_use_cases_are_read_and_built_back_with_the_same_nodes() -> None:
    model = parse_use_cases(PUML)
    assert model.system == "Гараж 61: онлайн-запись"
    assert ("ACT-03", "Администратор") in model.actors and len(model.use_cases) == 8
    assert ("ACT-02", "UC-06") in model.links and ("UC-05", "UC-04", "extend") in model.relations
    text = render_use_cases(model)
    assert scan_puml(text, "x.puml") == scan_puml(PUML, "x.puml")
    assert parse_use_cases(text) == model and render_use_cases(parse_use_cases(text)) == text


def test_garage61_workspace_is_read_and_built_back_with_the_same_nodes() -> None:
    model = parse_workspace(DSL)
    assert model.system is not None and model.system.id == "C4-SYS"
    assert [c.id for c in model.containers] == ["C4-CNT-01", "C4-CNT-02", "C4-CNT-03", "C4-CNT-04"]
    assert model.containers[2].database and model.containers[1].technology == "Python, FastAPI"
    assert [e.id for e in model.externals] == ["C4-EXT-01"]
    assert Relationship("C4-CNT-04", "C4-EXT-01", "Отправляет SMS", "HTTPS") in model.relations
    assert len(model.people) == 3 and len(model.relations) == 9
    text = render_workspace(model)
    assert scan_c4(text, "w.dsl") == scan_c4(DSL, "w.dsl")
    assert parse_workspace(text) == model and render_workspace(parse_workspace(text)) == text


def test_a_built_diagram_names_people_by_their_actor_ids() -> None:
    model = C4Model(
        title="Пекарня",
        system=Element("C4-SYS", "Заказы", "Приём заказов"),
        people=(Element("ACT-01", "Покупатель", 'Заказывает "торт"'),),
        containers=(Element("C4-CNT-01", "API", "Заказы", "Python", database=False),),
        externals=(Element("C4-EXT-01", "Платёжный шлюз", "Оплата картой"),),
        relations=(
            Relationship("ACT-01", "C4-CNT-01", "Заказывает", "HTTPS"),
            Relationship("C4-CNT-01", "C4-EXT-01", "Списывает оплату", ""),
        ),
    )
    text = render_workspace(model)
    assert '"reqgraph.id" "ACT-01"' in text and "act01 -> system.cnt01" in text
    assert "system.cnt01 -> ext01" in text and '"торт"' not in text  # quotes would break the DSL
    assert 'container system "containers"' in text
    assert parse_workspace(text).people[0].id == "ACT-01"
    alone = render_workspace(C4Model("Пекарня", model.system, model.people, (), (), ()))
    assert "container system" not in alone  # no container view without containers


def test_a_built_use_case_diagram_has_the_header_and_the_system_frame() -> None:
    model = UseCaseModel(
        system="Пекарня",
        actors=(("ACT-01", "Покупатель"),),
        use_cases=(UseCase("UC-01", "Заказать торт"), UseCase("UC-02", "Оплатить заказ")),
        links=(("ACT-01", "UC-01"), ("ACT-01", "UC-02")),
        relations=(("UC-02", "UC-01", "include"),),
    )
    text = render_use_cases(model)
    assert text.startswith("@startuml use_cases\n") and "СОБРАНО reqgraph" in text
    assert 'rectangle "Пекарня" {' in text and "UC02 .> UC01 : <<include>>" in text
    assert [n.id for n in scan_puml(text, "u.puml")] == ["UC-01", "UC-02"]
