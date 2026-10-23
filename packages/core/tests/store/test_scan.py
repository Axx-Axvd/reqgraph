"""Interim scanner of diagram files: ids and names by the conventions of garage61 (until T-104)."""

import pytest
from reqgraph.graph.store import StoreError
from reqgraph.graph.store.scan import scan_c4, scan_dbml, scan_puml

DBML = """
Table client {
  id int [pk, increment]
  phone varchar [unique, note: 'SMS']
  Note: 'ENT-01'
}

Table audit_log {
  id int [pk]
}
"""


def test_dbml_tables_with_an_entity_note() -> None:
    (ent,) = scan_dbml(DBML, "erd.dbml")
    assert (ent.id, ent.name) == ("ENT-01", "client")
    assert [(a.name, a.type) for a in ent.attributes] == [("id", "int"), ("phone", "varchar")]


def test_dbml_duplicate_entity_id() -> None:
    with pytest.raises(StoreError, match="ENT-01"):
        scan_dbml(DBML + DBML, "erd.dbml")


PUML = """@startuml
actor "Клиент" as ACT01
usecase "Записаться" as UC01
usecase "Отменить" as UC02
ACT01 --> UC01
UC02 .> UC01 : <<extend>>
@enduml
"""


def test_puml_use_cases_and_their_actor() -> None:
    found = {uc.id: uc for uc in scan_puml(PUML, "use_cases.puml")}
    assert (found["UC-01"].name, found["UC-01"].actor) == ("Записаться", "ACT-01")
    assert found["UC-02"].actor is None


def test_puml_without_use_cases() -> None:
    assert scan_puml("@startuml\nA -> B\n@enduml\n", "seq.puml") == []


C4 = """workspace {
    model {
        s = softwareSystem "Система" "Описание." {
            properties {
                "reqgraph.id" "C4-SYS"
            }
            web = container "Сайт" "Для клиентов." "Next.js" {
                properties {
                    "reqgraph.id" "C4-CNT-01"
                }
            }
        }
        sms = softwareSystem "SMS-шлюз" "Внешний." {
            properties {
                "reqgraph.id" "C4-EXT-01"
            }
        }
    }
}
"""


def test_c4_elements_by_property() -> None:
    found = {n.id: n for n in scan_c4(C4, "workspace.dsl")}
    assert (found["C4-SYS"].name, found["C4-SYS"].c4_kind) == ("Система", "system")
    cnt = found["C4-CNT-01"]
    assert (cnt.name, cnt.c4_kind, cnt.technology) == ("Сайт", "container", "Next.js")
    assert found["C4-EXT-01"].c4_kind == "external"


def test_c4_id_without_an_element() -> None:
    with pytest.raises(StoreError, match="C4-SYS"):
        scan_c4('properties {\n "reqgraph.id" "C4-SYS"\n}\n', "workspace.dsl")
