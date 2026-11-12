# 0001. Structure the package in inward-pointing layers

- **Status:** accepted
- **Date:** 2026-10-07 (proposed), 2026-10-08 (accepted)
- **Relates to:** README "Planned features"; amended by ADR 0008: SQL in the PostgreSQL
  adapter takes the place of Cypher in the Neo4j adapter, and the constraint checks run
  as SQL in that adapter instead of inside neo4aas. The split below holds unchanged.

## Context

The planned features (schema check, metamodel constraints via neo4aas, analytics, submodel template conformance, web UI, JSON/PDF reports) touch several external technologies: Neo4j with APOC, neo4aas, XSD/JSON-Schema validation, AASX/ZIP handling, PDF rendering, a web framework.

The `.claude/` tooling taken over from an earlier project already enforced a four-layer structure (`domain ← ports ← app ← adapters ← main.py`) through `.claude/architecture.json` and the `brick-check` hook. That structure came with the tooling and was not chosen for AASpect, so it started as *proposed*.

The question that settled it: **where does the analysis logic live?** If most checks were Cypher queries running inside Neo4j, the Python side would be mainly glue code and the pure `domain` layer would stay thin, so the layers would cost more than they return. If the analyses apply their rules in Python, there is substantial pure logic worth testing without infrastructure.

## Decision

Keep the four layers under `src/aaspect/`, with `main.py` as the only composition root, enforced by `brick-check`. For analyses over the graph, the line between layers is:

- **Cypher does what shrinks the data:** fetching, counting, grouping, and aggregates (`count`, `avg`, `stDev`, `percentileCont`). These queries live in the Neo4j adapter and return plain rows.
- **Python applies the rules:** classification (semanticId type and source, globalAssetId format), template conformance, version selection. These live in `domain` and are tested without Neo4j.
- The neo4aas constraint checker is Cypher inside neo4aas; AASpect calls it from an adapter.
  *Amended by ADR 0008:* the database is PostgreSQL, so the queries are SQL, and AASpect
  owns the constraint checks as SQL in its adapter.

## Consequences

**Good:** Classification and conformance rules are testable without a running Neo4j. Changes in how neo4aas stores the graph touch only the queries in one adapter, not the rules. This is already happening with neo4aas master, which no longer stores `modelType` as a property and stores single-entry lists as scalars. Swapping the schema library or the report format touches one adapter.

**Bad:** More files and indirection than a small tool strictly needs. For pure counting analyses (metamodel element types, language tags), the use-case is close to a pass-through: query, then table. Every new feature costs a Protocol plus wiring. Contributors unfamiliar with the pattern face a learning curve.

**Neutral:** Moving aggregation from Python into Cypher moves code from `domain` into the adapter but does not change the structure. `brick-check` rules and budgets follow the structure. Changing them means editing `.claude/architecture.json` and `CLAUDE.md`.

## Evidence

**Slice 1, schema check with web UI (2026-10-07).** Its logic runs in Python, and the layers paid off: `domain` holds the real rules (version selection, grouping of violations, report tables), all tested without files, workers or a server. Review fixes mostly stayed inside one brick: isolating validation in worker processes touched one adapter and one line of wiring, and the time limit per analysis touched only the use-case. The ports made fakes trivial.

**Earlier prototype analyses on neo4aas (read 2026-10-08).** These are the graph-based analyses AASpect will port. Every one splits the same way: Cypher fetches and counts, Python decides.

| Analysis | Cypher | Python |
|---|---|---|
| statistical, metamodel, multilanguage | counts, grouping, depth paths | percentages, depth statistics |
| asset, semantic identification | counts, distinct ids with counts | classification of id type and source (regex) |
| submodel analyser | submodels by idShort/semanticId | matching against template files on disk |
| template conformance (~1,000 lines, the largest) | one set-based extraction query per chunk | all rules (cardinality, modelType, valueType, idShort) |
| constraint check | all of it, inside neo4aas | grouping of violations |

The branch breaks the "Cypher shrinks the data" line twice: nesting depth returns one row per leaf element, and globalAssetIds come back ungrouped. Both move into Cypher aggregates when ported. Moving the rules themselves into Cypher was considered and rejected: rows are already grouped by distinct value, so it would gain almost nothing, and it would cost tests without Neo4j, mean the regexes follow Java rather than Python rules, and require templates in the graph (which is meant to hold only the corpus).

## Alternatives considered

| Option | Why not |
|---|---|
| Pure core plus everything else, with Protocols only where a fake is needed | Would fit if the rules lived in Cypher and `domain` stayed nearly empty. The prototype analyses show they do not. |
| One folder per feature (`compliance/`, `analytics/`, `templates/`), each with pure and I/O parts | Layering inside each folder would hold by convention only; shared pieces (Neo4j adapter, semanticId classification) would have no clear home. |
| No imposed structure | Superseded: features exist now, and the structure would otherwise be decided by accident. |

## Revisit when

An analysis needs its *rules* in Cypher, e.g. graph algorithms or resolving references across shells that cannot be done on fetched rows. Then check whether `domain` is still carrying weight or whether the lighter "pure core" option fits better.
