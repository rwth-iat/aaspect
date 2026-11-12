#!/bin/sh
# Runs once, when the server creates its data directory. AASpect logs in as `aaspect`, a
# role that may only create schemas in its own database: no superuser rights, so a flaw
# in a query cannot read server files, run programs or change the server. The limits
# bound the disk one server process of an analysis can fill and how long an abandoned
# transaction holds its locks, since the files analysed are uploaded by anyone. Only a
# superuser may raise temp_file_limit, so the role cannot.
# AASpect cancels the queries of an analysis at its time limit, 10 min by default
# (AASPECT_ANALYSIS_TIME_LIMIT_SECONDS). statement_timeout ends a query shortly after
# that even if AASpect died first; raise the two together.
# The superuser loses its password and is reachable only through the socket inside the
# container (`docker compose exec postgres psql`).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v app_password="$AASPECT_POSTGRES_PASSWORD" <<'SQL'
CREATE ROLE aaspect LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CREATE ON DATABASE aaspect TO aaspect;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
ALTER ROLE aaspect SET temp_file_limit = '5GB';
ALTER ROLE aaspect SET idle_in_transaction_session_timeout = '15min';
ALTER ROLE aaspect SET statement_timeout = '11min';
ALTER ROLE postgres PASSWORD NULL;
SQL
