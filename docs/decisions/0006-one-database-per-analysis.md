# 0006. Give every analysis its own database on a DozerDB server

- **Status:** superseded by 0008
- **Date:** 2026-10-13
- **Relates to:** README "Metamodel constraints", "Analytics", "Submodel template
  conformance", "Deployment"; ADR 0001, ADR 0002

## Context

The constraint check, analytics and template conformance all import a corpus into a graph
database and query it. AASpect will be hosted publicly, so two people can start an
analysis at the same time. If both corpora land in the same database, each analysis
counts and checks the other's data, and ADR 0002's rename-and-restore step on one corpus
breaks the links of the other. Every analysis therefore needs a graph of its own.

Neo4j Community Edition, which neo4aas targets, serves exactly one user database per
server. Three ways around that were compared on real corpus samples (up to 1,926 files,
857 MB, 5.2 M nodes), all running the neo4aas import, reference linking and all 25
constraint checks:

- **DozerDB** 5.26.27.0, a GPL-3.0 plugin for Neo4j Community 5.26 LTS that adds
  `CREATE DATABASE` / `DROP DATABASE`. Same graph and same findings as plain Neo4j, same
  speed (import 95 s vs 105 s, checks 18.6 s vs 18.2 s). Two corpora imported in
  parallel into separate databases gave results identical to single runs. All databases
  share one heap and page cache.
- **FalkorDB** 6.0.2, a different graph database that holds any number of graphs per
  server. neo4aas needed a second write path (FalkorDB has no APOC) and three query
  rewrites (`elementId`, `EXISTS { }` subqueries, Neo4j's constraint syntax); with those,
  graph and findings were identical to Neo4j. Import was 30–45 % faster and memory far
  lower on small corpora. On the larger sample, reference linking was 12x slower
  (18.2 s vs 1.5 s), all checks 2.6x (47.3 s vs 18.2 s), and AASd-129 alone went from
  0.2 s to 28 s; reversing the pattern did not help, so this is FalkorDB's query planner.
  It holds every graph fully in RAM (624 MB for the larger sample, 1.78 GB peak during
  import), where Neo4j keeps the store on disk and caches what fits. Its client splices
  parameters into the query text instead of sending them separately, and rejects a whole
  write batch over values Neo4j accepts (NUL characters, NaN, backticks in keys). Its
  license, SSPL, requires publishing the source of the whole service stack when "the
  functionality of the Program" is offered as a service; whether a hosted AASpect
  triggers that is untested.
- **One plain Neo4j container per analysis.** Needs no plugin, but AASpect would have to
  start and remove containers, which means access to the Docker daemon.

What was verified about DozerDB, and what it does not support: only the plain forms
`CREATE DATABASE name`, `DROP DATABASE name` and `NOWAIT` work (`IF NOT EXISTS`,
`IF EXISTS` and `WAIT` are rejected); a new database is online about 3 s after
`CREATE`; `DROP DATABASE $name` fails as a parameter while `CREATE DATABASE $name`
works; the server reports its edition as "enterprise".

## Decision

AASpect runs one DozerDB server (Neo4j Community 5.26 LTS with the DozerDB plugin and a
pinned APOC). Each analysis creates its own database, imports and queries only that
database, and drops it when the analysis has finished. AASpect names these databases
itself (a fixed prefix plus the analysis id); a name never comes from an uploaded file.
Before a name is used in an administration command, it is checked against Neo4j's naming
rule.

neo4aas opens every session on the server's default database. It gets a `database`
argument on its client, contributed upstream, so the database is chosen in one place.

## Consequences

**Good:** Analyses cannot see each other's data, and the ADR 0002 restore stays local to
one corpus. Only one database container has to be run and monitored. Memory is shared, so
an idle or small analysis does not reserve a full Neo4j heap. The license is the same as
Neo4j Community's, so public hosting raises no new license question. neo4aas runs
unchanged apart from the database argument.

**Bad:** AASpect depends on a small project: one sponsoring company, best-effort support,
releases months apart, and only the Neo4j 5.26 LTS line, so newer Neo4j releases are out
of reach while DozerDB is used. Its administration commands differ from Neo4j
Enterprise's (no `IF EXISTS`, no `WAIT`), so AASpect has to check existence and status
itself. Database names end up in query text because `DROP` does not take a parameter;
the naming check is what keeps that safe. A crash between `CREATE` and `DROP` leaves a
database behind, so AASpect must drop leftover databases with its prefix at startup.
Parallel analyses share one heap, so the number running at once has to be limited to fit
the server's memory.

**Neutral:** The constraint checker, queries and import code are the same as on plain
Neo4j; only how a session picks its database changes. Switching to FalkorDB later stays
contained: all graph access sits in AASpect's graph adapter (ADR 0001), so the analyses
would not change. The work would be a FalkorDB write path and the three query rewrites in
neo4aas, both already shown to work, plus FalkorDB's own way of creating and dropping a
graph in that adapter.

## Alternatives considered

| Option | Why not |
|---|---|
| FalkorDB | Results identical and import faster, but linking and some checks much slower on larger graphs, every graph fully in RAM, no APOC, weaker input handling, and an SSPL question for public hosting. Remains the alternative if those change. |
| One plain Neo4j container per analysis | AASpect would need control of the Docker daemon, which on a public server is close to root access; each analysis reserves its own heap and starts in seconds. Kept as the fallback if DozerDB is abandoned, since only database selection changes. |
| One shared database, analyses queued one at a time | Users wait for every other corpus to be imported and checked. |
| Neo4j Enterprise | Not open source; its license does not fit a freely hosted open-source tool. |

## Revisit when

- DozerDB has no release for a Neo4j 5.26 patch within a few months, or neo4aas needs a
  Neo4j feature newer than 5.26: switch to one container per analysis, or to FalkorDB.
- Real corpora on the hosted server need more memory than one shared heap can give to
  the analyses running at once.
- FalkorDB's linking and variable-length checks become competitive on large graphs, or
  its license question is settled for public hosting.
- The upstream `database` argument is rejected: keep the driver wrapper in AASpect's
  graph adapter instead.
