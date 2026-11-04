"""The schema one analysis keeps its graph in: its name and its tables."""

import re
import uuid

from psycopg import sql

PREFIX = "aaspect_"
# Lower case, so the name means the same quoted or not; PostgreSQL cuts names at 63 bytes.
_SCHEMA_NAME = re.compile(r"[a-z][a-z0-9_]{2,62}")

# Hash indexes for id and hash: a btree entry may hold at most 2,704 bytes, and both
# values come from the uploaded files, so a long id would make the upload fail.
_CREATE = """
CREATE SCHEMA {s};
CREATE SEQUENCE {s}.node_ids;
CREATE TABLE {s}.nodes (id bigint PRIMARY KEY, labels text[] NOT NULL, props jsonb NOT NULL);
CREATE TABLE {s}.edges (
    start_id bigint NOT NULL, end_id bigint NOT NULL, type text NOT NULL, props jsonb NOT NULL
);
CREATE INDEX ON {s}.nodes USING gin (labels);
CREATE INDEX ON {s}.nodes USING hash ((props->>'id'));
CREATE INDEX ON {s}.nodes USING hash ((props->>'hash'));
CREATE INDEX ON {s}.edges (start_id, type);
CREATE INDEX ON {s}.edges (end_id, type);

-- An uploaded file can put any JSON value where text, a list or a number belongs, and
-- neo4aas stores keys it does not know. The queries only use a value of the right type.
CREATE FUNCTION {s}.text_of(value jsonb, prefix int) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN CASE WHEN jsonb_typeof(value) = 'string' THEN left(value #>> '{{}}', prefix) END;
CREATE FUNCTION {s}.first_key(props jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN CASE WHEN jsonb_typeof(props->'keys_value') = 'array'
                THEN props->'keys_value'->0 END;
CREATE FUNCTION {s}.whole_number(value jsonb) RETURNS bigint
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN CASE WHEN jsonb_typeof(value) = 'number' AND value::text ~ '^-?[0-9]{{1,18}}$'
                THEN value::text::bigint END;
"""


def new_name() -> str:
    return checked(PREFIX + uuid.uuid4().hex)


def checked(name: str) -> str:
    """`name`, if it is one AASpect could have generated; raises `ValueError` otherwise."""
    if not _SCHEMA_NAME.fullmatch(name) or not name.startswith(PREFIX):
        raise ValueError(f"not a valid schema name: {name!r}")
    return name


def create(name: str) -> sql.Composed:
    return sql.SQL(_CREATE).format(s=sql.Identifier(checked(name)))


def drop(name: str) -> sql.Composed:
    return sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(checked(name)))
