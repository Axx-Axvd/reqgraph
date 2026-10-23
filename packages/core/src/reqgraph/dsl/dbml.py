"""ERD as DBML, read with pydbml (base of SCH-003). Tables with `Note: 'ENT-xx'` are entities."""

import re
from dataclasses import dataclass

from pydbml import PyDBML
from pyparsing import ParseBaseException

from reqgraph.dsl.process import DslError
from reqgraph.graph.errors import GraphError
from reqgraph.graph.nodes import EntityNode, node_from_dict

_ENTITY_ID = re.compile(r"ENT-\d{2,}")


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    pk: bool = False
    not_null: bool = False
    unique: bool = False
    note: str | None = None


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    note: str | None = None

    @property
    def entity_id(self) -> str | None:
        """ENT-xx when the table note is exactly an entity id (REVIEW.md of garage61, No. 3)."""
        text = (self.note or "").strip()
        return text if _ENTITY_ID.fullmatch(text) else None


@dataclass(frozen=True)
class Relation:
    src_table: str
    src_columns: tuple[str, ...]
    kind: str  # pydbml: '>' many-to-one, '<' one-to-many, '-' one-to-one, '<>' many-to-many
    dst_table: str
    dst_columns: tuple[str, ...]


@dataclass(frozen=True)
class DataModel:
    tables: tuple[Table, ...]
    relations: tuple[Relation, ...]
    enums: dict[str, tuple[str, ...]]


def _note(obj: object) -> str | None:
    note = getattr(obj, "note", None)
    text = getattr(note, "text", None) if note is not None else None
    return str(text) if text else None


def parse_dbml(text: str, path: str) -> DataModel:
    """Parse with pydbml; any error becomes DslError «file, строка N: reason»."""
    try:
        database = PyDBML(text)
    except ParseBaseException as exc:
        raise DslError(f"{path}, строка {exc.lineno}: DBML не разобран: {exc.msg}") from None
    except Exception as exc:  # pydbml raises its own errors for refs to missing tables etc.
        raise DslError(f"{path}: DBML не разобран: {exc}") from None
    tables = tuple(
        Table(
            name=table.name,
            note=_note(table),
            columns=tuple(
                Column(
                    name=column.name,
                    type=str(column.type),
                    pk=bool(column.pk),
                    not_null=bool(column.not_null),
                    unique=bool(column.unique),
                    note=_note(column),
                )
                for column in table.columns
            ),
        )
        for table in database.tables
    )
    relations = tuple(
        Relation(
            src_table=ref.col1[0].table.name,
            src_columns=tuple(c.name for c in ref.col1),
            kind=ref.type,
            dst_table=ref.col2[0].table.name,
            dst_columns=tuple(c.name for c in ref.col2),
        )
        for ref in database.refs
    )
    enums = {enum.name: tuple(item.name for item in enum.items) for enum in database.enums}
    return DataModel(tables=tables, relations=relations, enums=enums)


def entities(model: DataModel, path: str) -> list[EntityNode]:
    """Entity nodes of the graph: one per table with an ENT note, columns as attributes."""
    found: dict[str, EntityNode] = {}
    for table in model.tables:
        entity_id = table.entity_id
        if entity_id is None:
            continue
        if entity_id in found:
            raise DslError(f"{path}: {entity_id} встречается в двух таблицах")
        attributes = [{"name": c.name, "type": c.type, "note": c.note} for c in table.columns]
        data = {"kind": "ENT", "id": entity_id, "name": table.name, "attributes": attributes}
        try:
            node = node_from_dict(data, f"{path}: {entity_id}")
        except GraphError as exc:
            raise DslError(str(exc)) from None
        assert isinstance(node, EntityNode)
        found[entity_id] = node
    return list(found.values())


def attribute_refs(model: DataModel) -> set[str]:
    """`ENT-05.status`: references to attributes that requirements may use (realized_by)."""
    return {
        f"{table.entity_id}.{column.name}"
        for table in model.tables
        if table.entity_id
        for column in table.columns
    }


def read_entities(text: str, path: str) -> list[EntityNode]:
    """Reader for FileStore: the entity nodes of a .dbml file."""
    return entities(parse_dbml(text, path), path)
