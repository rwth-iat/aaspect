"""neo4aas's mapping of AAS JSON to nodes and edges, written to the tables of one schema.

neo4aas has no public way to get the mapped graph without writing it to Neo4j, so this
overrides three of its internals: `session`, `_stored_identifiable_ids` and
`_write_graph`, and wraps `_process_dict` so that a mapping fault refuses the content.
Everything before the write (mapping, deduplication, skipping an Identifiable already
stored) stays neo4aas's own, so the graph matches the Neo4j one.
"""

import contextlib
import dataclasses
import json
from collections.abc import Iterable, Sequence
from typing import Any, LiteralString

import psycopg
from neo4aas.core.client import AAS_NEO4J_MODEL_CONFIG, AASNeo4JClient
from psycopg import sql

from aaspect.adapters.postgres import schema
from aaspect.adapters.postgres.errors import content_fault
from aaspect.domain.id_collisions import Environment

# Without the uniqueness constraint, so that collision variants can share their id once
# it is restored. Repeats are still merged by id during the import.
_MODEL_CONFIG = dataclasses.replace(AAS_NEO4J_MODEL_CONFIG, enforce_unique_ids=False)
_IDENTIFIABLE_LISTS = ("assetAdministrationShells", "submodels", "conceptDescriptions")


class ContentRefused(ValueError):
    """The content cannot be stored; the message names why without quoting it."""


class WriteFailed(RuntimeError):
    """The write itself broke on content the database would take: a fault of this code,
    which must fail the step instead of blaming every document."""


class GraphWriter(AASNeo4JClient):
    def __init__(self, connection: psycopg.Connection, name: str) -> None:
        super().__init__("", "", model_config=_MODEL_CONFIG, auto_optimize=False)
        self._connection = connection
        self._schema = sql.Identifier(schema.checked(name))

    def _sql(self, template: LiteralString) -> sql.Composed:
        return sql.SQL(template).format(s=self._schema)

    def upload(self, environments: Sequence[Environment]) -> None:
        """Store the environments in one transaction. Raises `ValueError`, having stored
        none of them, if their content cannot be stored."""
        # neo4aas reads only the three Identifiable lists, so joining them is the same as
        # uploading each environment. One call is one transaction.
        merged = {key: _entries(environments, key) for key in _IDENTIFIABLE_LISTS}
        _id_shorts_as_text(merged)
        try:
            self.upload_json(merged)
        except (ContentRefused, WriteFailed):
            raise
        except Exception as error:
            reason = content_fault(error)
            if reason:
                raise ValueError(reason) from error
            if isinstance(error, psycopg.Error):
                raise
            # neo4aas trusts the structure it is given; schema-invalid content fails with
            # whatever error the first unexpected value causes.
            raise ValueError(f"content cannot be stored: {type(error).__name__}") from error

    def _process_dict(self, obj: dict, node_properties: dict | None = None) -> Any:
        # neo4aas skips the rest of an Identifiable list on a KeyError, such as an unknown
        # modelType, and stores the part before it as if it were the whole document.
        try:
            return super()._process_dict(obj, node_properties)
        except KeyError as error:
            raise ContentRefused(f"content cannot be stored: {type(error).__name__}") from error

    def session(self, **_: Any) -> Any:
        # neo4aas opens a session around `_write_graph`; the write needs none.
        return contextlib.nullcontext()

    def _stored_identifiable_ids(self, ids: list[str]) -> set:
        return {value for value, _ in self._typed_lookup(("Identifiable",), "id", ids)}

    def _write_graph(
        self,
        session: Any,
        grouped_nodes: dict,
        relationships: dict,
        exist_uid_to_internal_id: dict | None = None,
    ) -> int:
        try:
            return self._write(grouped_nodes, relationships, exist_uid_to_internal_id or {})
        except (ContentRefused, psycopg.Error, UnicodeEncodeError):
            raise
        except Exception as error:
            raise WriteFailed(type(error).__name__) from error

    def _write(self, grouped_nodes: dict, relationships: dict, existing: dict) -> int:
        create, by_hash, by_id, create_rels, merge_rels = self._write_buckets(
            grouped_nodes, relationships, existing
        )
        ids = {str(uid): int(node) for uid, node in existing.items()}
        with self._connection.transaction():
            fresh = [
                (row["uid"], key, row["props"]) for key, rows in create.items() for row in rows
            ]
            aliases: list[tuple[str, str]] = []
            for buckets, field in ((by_hash, "hash"), (by_id, "id")):
                for key, rows in buckets.items():
                    fresh += self._merged(key, rows, field, ids, aliases)
            self._copy_nodes(fresh, ids)
            ids.update((alias, ids[original]) for alias, original in aliases)
            edges = [
                _edge(rel_type, row, ids) for rel_type, rows in create_rels.items() for row in rows
            ]
            edges += self._new_edges([_edge(rel["type"], rel, ids) for rel in merge_rels])
            with self._connection.cursor().copy(
                self._sql("COPY {s}.edges (start_id, end_id, type, props) FROM STDIN")
            ) as copy:
                for edge in edges:
                    copy.write_row(edge)
        return len(edges)

    def _merged(
        self, key: str, rows: list, field: str, ids: dict, aliases: list[tuple[str, str]]
    ) -> list[tuple[str, str, dict]]:
        """Map rows onto stored nodes with the same labels and `field` value, as Neo4j's
        MERGE does; return the others once each. A repeat within the batch becomes an
        alias of its first row."""
        if field == "id" and any(row["props"].get("id") is None for row in rows):
            # Neo4j refuses to merge on a missing id; here every such object would merge
            # into one node.
            raise ContentRefused("content cannot be stored: an Identifiable has no id")
        labels = tuple(key.split(","))
        stored = self._typed_lookup(labels, field, [row["props"][field] for row in rows])
        found = {_canonical(value): node for value, node in stored}
        fresh, first_uid = [], {}
        for row in rows:
            value = _canonical(row["props"][field])
            if value in found:
                ids[row["uid"]] = found[value]
            elif value in first_uid:
                aliases.append((row["uid"], first_uid[value]))
            else:
                first_uid[value] = row["uid"]
                fresh.append((row["uid"], key, row["props"]))
        return fresh

    def _typed_lookup(
        self, labels: Sequence[str], field: str, values: Iterable[Any]
    ) -> list[tuple[Any, int]]:
        """Stored nodes with all `labels` whose `field` equals one of `values` in type and
        content: Neo4j tells the number 5 from the text "5", so this does too."""
        texts = sorted({_text(value) for value in values})
        if not texts:
            return []
        rows = self._connection.execute(
            self._sql(
                "SELECT props->%s, id FROM {s}.nodes"
                " WHERE labels @> %s::text[] AND props->>%s = ANY(%s)"
            ),
            (field, list(labels), field, texts),
        ).fetchall()
        wanted = {_canonical(value) for value in values}
        return [(value, node) for value, node in rows if _canonical(value) in wanted]

    def _copy_nodes(self, nodes: list[tuple[str, str, dict]], ids: dict) -> None:
        if not nodes:
            return
        numbers = self._connection.execute(
            self._sql("SELECT nextval('{s}.node_ids') FROM generate_series(1, %s)"), (len(nodes),)
        ).fetchall()
        with self._connection.cursor().copy(
            self._sql("COPY {s}.nodes (id, labels, props) FROM STDIN")
        ) as copy:
            for (uid, key, props), (node_id,) in zip(nodes, numbers, strict=True):
                ids[uid] = node_id
                copy.write_row((node_id, key.split(","), _props(props)))

    def _new_edges(self, edges: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
        """Leave out edges already stored with the same ends, type and properties, as
        Neo4j's MERGE does for the edges of a content-deduplicated node."""
        if not edges:
            return []
        stored = self._connection.execute(
            self._sql(
                "SELECT start_id, end_id, type, props FROM {s}.edges WHERE start_id = ANY(%s)"
            ),
            (sorted({edge[0] for edge in edges}),),
        ).fetchall()
        seen = {(start, end, kind, _canonical(props)) for start, end, kind, props in stored}
        new = []
        for start, end, kind, props in edges:
            key = (start, end, kind, _canonical(json.loads(props)))
            if key not in seen:
                seen.add(key)
                new.append((start, end, kind, props))
        return new


def _edge(rel_type: str, row: dict, ids: dict) -> tuple[int, int, str, str]:
    return ids[row["from"]], ids[row["to"]], rel_type, json.dumps(row["props"], ensure_ascii=False)


def _props(props: dict) -> str:
    # Neo4j stores no null property; the queries rely on an absent key meaning null.
    return json.dumps({k: v for k, v in props.items() if v is not None}, ensure_ascii=False)


def _canonical(value: Any) -> str:
    """A key that differs for values Neo4j tells apart, such as 5 and "5"."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _text(value: Any) -> str:
    """The value as `props->>field` gives it back."""
    return value if isinstance(value, str) else _canonical(value)


def _id_shorts_as_text(environment: Environment) -> None:
    """The checks compare idShorts with text, and fail on anything else. The schema check
    reports the wrong type; as text, the value is still checked against the pattern. Done
    at upload, after the id scan, so that `1` and `"1"` still count as different content."""
    # Iterative: uploaded documents can nest deeper than Python's recursion limit.
    pending: list[Any] = [environment]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            id_short = item.get("idShort")
            if id_short is not None and not isinstance(id_short, str):
                item["idShort"] = json.dumps(id_short, ensure_ascii=False)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _entries(environments: Sequence[Environment], key: str) -> list:
    joined = []
    for environment in environments:
        entries = environment.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"content cannot be stored: {key} is not a list")
        joined.extend(entries)
    return joined
