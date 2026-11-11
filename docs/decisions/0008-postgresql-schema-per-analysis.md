# 0008. Store each analysis in its own PostgreSQL schema and own the checks as SQL

- **Status:** provisional — pending verification
- **Date:** 2026-11-04
- **Relates to:** README "Metamodel constraints", "Analytics", "Submodel template
  conformance", "Deployment"; supersedes ADR 0006; amends ADR 0001 and ADR 0002

## Context

Every graph analysis imports a corpus and queries it, and analyses from different people
run at the same time on the public server, so each needs data of its own (ADR 0006).
ADR 0006 met that with DozerDB. That leaves AASpect on a small one-company project, tied
to Neo4j 5.26. Database names also end up in query text, because `DROP DATABASE` takes
no parameter.

A local benchmark (neo4aas `255fd6a`, 2026-11) loaded the same graph into seven
databases. Each ran the 29 checks of neo4aas's `validation.py` and three analytic
queries, one instance at a time. On every set, all seven gave the same violation counts
and analytic results. Results for per-vendor-500 (4,626 files, 2.1 GB, 4,553 AAS), run
under WSL2 on Windows; native Linux numbers are under Evidence:

| | Upload | All 29 checks | Peak DB memory |
|---|---|---|---|
| Neo4j / DozerDB | 344 s / 365 s | 64 s | 5.7 GB |
| PostgreSQL, two tables (`nodes`, `edges`, `jsonb` props) | 287 s | 15 s | 2.9 GB |

57 of Neo4j's 64 s are AASd-002: neo4aas pulls every idShort into Python for its regex.
The same Python step drives the worker's memory (2.8 GB). Its regex backtracks
quadratically on long idShorts and blocks the app. In SQL, the check takes 2.1 s inside
the database.

What is **not** verified yet: three or more analyses at once (the concurrent benchmark
did not fit the test machine); equivalence beyond violation *counts* on three sets; and
how PostgreSQL treats hostile input. `text` and `jsonb` reject `\u0000`, which Neo4j
stores.

## Decision

AASpect runs one PostgreSQL server. Each analysis gets its own schema, holding the tables
`nodes(id, labels, props jsonb)` and `edges(start_id, end_id, type, props jsonb)`. AASpect
names the schema itself: a fixed prefix plus the analysis id, checked against a name
rule. Name and values go in only via `psycopg.sql.Identifier` and query parameters. The
schema is dropped when the analysis ends, and leftovers carrying the prefix are dropped
at startup.

AASpect owns the metamodel constraint checks as SQL, one rule set per metamodel version.
It also owns reference linking, the ADR 0002 restore, analytics and submodel trees.
neo4aas stays only for turning AAS JSON into nodes and edges and for `xml_to_json`.

## Consequences

**Good:** An OSI license (PostgreSQL), a large project with long-term support, and no
plugin. Every name goes through `sql.Identifier`, including `DROP`. The database needs
half the memory and the worker less than half. Speed is about even. Upload is roughly
the same on native Linux. All checks take 12 s against 41 s, but only because of
neo4aas's AASd-002; without it, Neo4j is faster (5 s vs 11 s, see Evidence). AASd-002's regex runs in the database, so the
quadratic Python regex and the worker's memory peak disappear. A check can stop at
AASpect's cap of places instead of returning every violation. A query past the time
limit is cancelled with `pg_cancel_backend`, by the connection's name; `statement_timeout`
was not used, as one limit per statement does not bound an analysis of many. The server
bounds what the files can make a query take instead: the app's role may hold at most 5 GB
of temporary files per process and cannot raise that. ADR 0002's restore needs no neo4aas
option to skip a UNIQUE constraint, because AASpect defines the tables.

**Bad:** neo4aas's fixes and new rules no longer arrive by bumping the pin. Each one has to
be ported to SQL by hand, and AASpect's checks can drift from upstream unnoticed. 29
checks across three versions become AASpect code to test and maintain. The write path
overrides neo4aas's private `_write_graph` and stubs its Neo4j driver, so a neo4aas
refactor can break it silently. A public mapping API upstream would end that. Queries
are SQL over `jsonb` and recursive CTEs, which are longer and harder to read than Cypher
paths. All schemas share one server's memory, so analyses at once still need a limit. A
file containing `\u0000` must be refused as a content fault before upload.

**Neutral:** Ports do not change (`GraphStore`, `AnalysisGraph`); the work is one new
adapter package, configuration, wiring and deployment. ADR 0001's split still holds with
SQL in place of Cypher, but the constraint checks move from "inside neo4aas" to AASpect's
adapter.

## Alternatives considered

| Option | Why not |
|---|---|
| Stay on DozerDB, fix AASd-002 upstream | Closes most of the check gap and keeps neo4aas's checker, but keeps the DozerDB/5.26 dependency, Neo4j's memory, and names in query text. |
| PostgreSQL + Apache AGE (Cypher) | Checks still needed rewriting, two in SQL anyway; AASd-022 took 45 s on per-vendor-500. |
| FalkorDB, Memgraph, ArangoDB | Source-available licenses (SSPL, BSL) with restrictions on offering them as a service; each had checks 5–30x slower on the largest set. |
| One plain Neo4j container per analysis | Needs Docker daemon access from a public app; a full heap per analysis. |

## Evidence

**Single runs on native Linux (2026-11-04, 16 threads / 32 GB, same images and limits as the
WSL2 runs: database 8 GB / 8 CPUs, worker 4 GB / 4 CPUs), per-vendor-500.** Neo4j and
PostgreSQL gave identical results, and each matched its own WSL2 run.

| | Upload (JSON / XML / AASX) | All checks | Without AASd-002 | Analytics | Peak DB / worker |
|---|---|---|---|---|---|
| Neo4j 2026.10.0 | 237 s (89 / 126 / 22) | 41.4 s | 4.8 s | 1.0 s | 5.7 / 2.7 GiB |
| PostgreSQL 18.6 | 226 s (62 / 144 / 19) | 12.2 s | 11.0 s | 2.5 s | 2.7 / 1.1 GiB |

WSL2 had inflated Neo4j's upload (344 s); natively, the two are about even. Without
AASd-002 (36.6 s on Neo4j, 1.2 s on PostgreSQL), the hand-written SQL is slower than
Cypher. The largest gaps are AASd-022 (6.1 vs 2.4 s), AASd-114 (1.8 vs 0.05 s), AASd-117
(1.2 vs 0.25 s) and AASd-129 (0.6 vs 0.2 s). These are worth tuning when the checks are
ported.

**Concurrent run (2026-11-04, native Linux, 16 threads / 32 GB).** One PostgreSQL server
(10 GB, 6 CPUs), three workers (2 GB, 2 CPUs each), each importing per-vendor-500 into its
own schema at the same time, then running all checks and analytics. All 32 results of
each analysis were identical to a single run, and the single run matched the earlier
WSL2 run. There were no OOM kills and no cap breaches. Peaks: server 5.0 GiB, 609 % CPU;
each worker 1.1 GiB.

| | Upload | All checks | Analytics |
|---|---|---|---|
| Single run (8 GB, 8 CPUs) | 226 s | 12.2 s | 2.5 s |
| Each of three at once | 454–459 s | 14.5–15.1 s | 5.4–5.5 s |

Upload is about twice as slow under contention, because the server is CPU-bound at its 6
CPUs. Three analyses still finished in 571 s, against 3 × ~300 s run one after another.
The checks barely slow down.

**Hostile input (2026-11-04).** 25 crafted environments were sent through the bench write
path to both databases. Each successful upload was followed by linking and all 29 checks.
Neither server crashed or ran out of memory. Every refusal hit only the upload it came
from, and stored nothing, because `upload_json` writes in one transaction.

| Input | PostgreSQL | Neo4j |
|---|---|---|
| NUL in a value, idShort, id, key or reference key | refused (`22P05`, or psycopg `DataError` for `\x00` in a text column) | stored (refused only in a key) |
| NaN, Infinity | refused (`22P02`) | stored |
| Integer of 2^80 | stored | refused (`OverflowError` in the driver) |
| Lone surrogate `\ud800` | refused (`UnicodeEncodeError` in Python) | the same |
| Incompressible id of 3k chars | refused: btree row > 2,704 bytes (`54000`) | stored |
| Id or semanticId of 10k chars, idShort of 10k chars | id refused (`54000`); others stored | all refused (index/property size) |
| Backtick or empty keys | stored | refused (APOC) |
| SQL/Cypher metacharacters in idShort and value | stored unchanged | stored unchanged |
| 20 MB random / 50 MB value, 100k elements | stored, checks pass | stored, checks pass |
| Nesting 200 / 300 | stored / `RecursionError` in neo4aas | the same |

For the adapter, this means:
- **Content faults:** SQLSTATE `22P05`, `22P02` and `54000`, psycopg `DataError`, and
  `UnicodeEncodeError` are the document's fault. Anything else fails the step, as today.
- **Ids:** index `id` and `hash` by a digest (`md5(props->>'id')`) or with `USING hash`.
  Otherwise PostgreSQL refuses ids that Neo4j stores.
- **NUL and NaN:** files that Neo4j analyses today get refused. Name the reason in the
  report instead of a database message. Nesting, reference length and object count are
  already capped before upload.

**Self-holding References (2026-11-05).** The probes above missed one shape. neo4aas
merges References by their own fields only, so a Reference whose `referredSemanticId`
has the same keys becomes one node holding itself. The first SQL walks for places and
affected counts followed that loop to their depth limit: 2.4 KB of schema-valid JSON
wrote 9.1 GB of temporary files in 66 s, and three affected elements counted as 27. The
walks now collect the holding References as a set. The same file takes 0.01 s; a 10.5 MB
file built so that 200 References all hold each other takes 55 s and writes 570 MB of
temporary files in total. Results on per-vendor-100 did not change.

**Full-findings equivalence (2026-11-05).** The whole analysis ran through AASpect's own
use case once on DozerDB and once on the new PostgreSQL adapter. Both used the same
schemas, templates and uploads, and the JSON reports were compared block by block.
Runs: per-vendor-10 and per-vendor-500 with automatic version choice, and per-vendor-100
with automatic choice, 3.1 and 3.2. Schema check, graph import, rule totals, analytics and
template totals were identical in every run. The differences were all of three kinds:

- **Which locations a capped list keeps.** Constraint findings keep 1,000 places, and
  template findings keep 500 findings and 1,000 places each. Neo4j returns violations in
  storage order, while the SQL adapter sorts them by node. Totals and "not listed" counts
  still match.
- **The order of locations** within a finding, for the same reason.
- **A median of `4` vs `4.0`.** Neo4j's `percentileCont` returns an integer when the
  median is whole; PostgreSQL always returns a float, as `Spread.median` declares.

Two PostgreSQL runs of the same corpus first differed in which ties made the template cap,
because submodels came back in no fixed order. They now come in storage order, and two
runs give byte-identical reports.

Server settings matter more than the queries. With the image's defaults (128 MB shared
buffers, 4 MB work_mem, 2 GB container), analytics took 134 s and template reads 80 s on
per-vendor-500, against Neo4j's 16 s and 58 s. With the bench settings (8 GB container,
2 GB shared buffers, 128 MB work_mem), the whole analysis on per-vendor-500 took:

| | Schema | Import | Analytics | Templates | Constraints | Total |
|---|---|---|---|---|---|---|
| DozerDB (4 GB heap, 2 GB page cache) | 39 s | 275 s | 16 s | 58 s | 41 s | 434 s |
| PostgreSQL 18.6, bench settings | 39 s | 232 s | 37 s | 35 s | 12 s | 356 s |

Two analytics queries were then rewritten, with identical rows on per-vendor-100: leaf
depth (2x faster) and attribute use (6x faster). Deployment must therefore set the server
memory explicitly, not leave the image defaults.

## Revisit when

- ~~**Concurrent run:** three analyses on per-vendor-500 at once on one server, with
  results identical to single runs and memory within the server's limit.~~ Done, see
  Evidence.
- ~~**Equivalence:** full findings (rule, element, place) from the SQL checks equal the
  Neo4j adapter's on all three benchmark sets, before the Neo4j adapter is removed.~~
  Done, see Evidence; differences only in what a capped list keeps.
- ~~**Hostile input:** NUL characters, NaN, huge strings and odd keys are refused as
  content faults, not as database errors.~~ Probed, see Evidence; the content-fault list
  there must be covered by the adapter's tests.
- neo4aas changes `_write_graph` or adds a public mapping API.
- neo4aas adds or changes a constraint rule: port it, or reopen this decision if porting
  becomes the bulk of the work.
