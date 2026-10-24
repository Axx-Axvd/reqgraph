"""ERD in DBML through pydbml: entities, attributes, relations, enums (T-104, base of SCH-003)."""

import pytest
from reqgraph.dsl.dbml import (
    Column,
    DataModel,
    Relation,
    Table,
    attribute_refs,
    entities,
    parse_dbml,
    render_dbml,
)
from reqgraph.dsl.process import DslError

from .conftest import GARAGE61

ERD = GARAGE61.parent / "data" / "erd.dbml"


def test_reference_model() -> None:
    model = parse_dbml(ERD.read_text(encoding="utf-8"), "models/data/erd.dbml")
    assert [t.name for t in model.tables][:3] == ["client", "service", "car"]
    assert model.enums["booking_status"] == ("confirmed", "cancelled", "no_show", "done")
    assert ("car", ("client_id",), "client", ("id",)) in {
        (r.src_table, r.src_columns, r.dst_table, r.dst_columns) for r in model.relations
    }


def test_entities_carry_their_columns() -> None:
    model = parse_dbml(ERD.read_text(encoding="utf-8"), "models/data/erd.dbml")
    found = {e.id: e for e in entities(model, "erd.dbml")}
    assert len(found) == 8
    client = found["ENT-01"]
    assert client.name == "Клиент"  # `Note: 'ENT-01 · Клиент'`: the Russian name of the entity
    phone = next(a for a in client.attributes if a.name == "phone")
    assert (phone.type, phone.note) == ("varchar", "подтверждён SMS-кодом (FR-004)")


def test_attribute_references() -> None:
    model = parse_dbml(ERD.read_text(encoding="utf-8"), "models/data/erd.dbml")
    assert "ENT-05.status" in attribute_refs(model)


def test_syntax_error_names_the_file_and_line() -> None:
    # pyparsing reports the line where it noticed the problem: the unclosed `[` of line 3 on 4
    with pytest.raises(DslError, match=r"erd\.dbml, строка 4: DBML не разобран: Expected '\]'"):
        parse_dbml("Table a {\n  id int\n  name varchar [unique\n}\n", "erd.dbml")


def test_reference_to_a_missing_table() -> None:
    with pytest.raises(DslError, match=r"erd\.dbml"):
        parse_dbml("Table a {\n  id int\n}\nRef: a.id > b.id\n", "erd.dbml")


def test_table_without_entity_note_is_not_an_entity() -> None:
    model = parse_dbml("Table audit {\n  id int\n}\n", "erd.dbml")
    assert entities(model, "erd.dbml") == []


@pytest.mark.parametrize(
    ("note", "name"),
    [
        ("ENT-01", "client"),
        ("ENT-01 · Клиент", "Клиент"),
        ("ENT-01·Смена мастера", "Смена мастера"),
    ],
)
def test_entity_name_from_the_note(note: str, name: str) -> None:
    model = parse_dbml(f"Table client {{\n  id int\n  Note: '{note}'\n}}\n", "erd.dbml")
    (entity,) = entities(model, "erd.dbml")
    assert (entity.id, entity.name) == ("ENT-01", name)


def test_note_that_only_mentions_an_id_is_not_an_entity() -> None:
    model = parse_dbml("Table log {\n  id int\n  Note: 'см. ENT-01'\n}\n", "erd.dbml")
    assert entities(model, "erd.dbml") == []


def test_duplicate_entity_id() -> None:
    text = "Table a {\n  id int\n  Note: 'ENT-01'\n}\nTable b {\n  id int\n  Note: 'ENT-01'\n}\n"
    with pytest.raises(DslError, match="ENT-01"):
        entities(parse_dbml(text, "erd.dbml"), "erd.dbml")


def test_render_round_trips_the_reference_model() -> None:
    """The Modeler's ERD is written by code: parse(render(model)) gives the same model (T-203)."""
    model = parse_dbml(ERD.read_text(encoding="utf-8"), "erd.dbml")
    text = render_dbml(model)
    assert parse_dbml(text, "erd.dbml") == model
    assert entities(parse_dbml(text, "erd.dbml"), "erd.dbml") == entities(model, "erd.dbml")


def test_render_quotes_notes_and_names() -> None:
    model = DataModel(
        tables=(
            Table(
                name="client",
                note="ENT-01 · Клиент",
                columns=(
                    Column("id", "int", pk=True),
                    Column(
                        "phone", "varchar", not_null=True, unique=True, note="код из SMS, 'кавычки'"
                    ),
                ),
            ),
            Table(name="visit", note="ENT-02 · Визит", columns=(Column("client_id", "int"),)),
        ),
        relations=(Relation("visit", ("client_id",), ">", "client", ("id",)),),
        enums={"visit_status": ("planned", "done")},
    )
    text = render_dbml(model)
    assert "Note: 'ENT-01 · Клиент'" in text and "\\'кавычки\\'" in text
    assert parse_dbml(text, "erd.dbml") == model
