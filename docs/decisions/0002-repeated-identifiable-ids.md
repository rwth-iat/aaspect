# 0002. Handle repeated Identifiable ids on import

- **Status:** accepted (2026-10-12)
- **Date:** 2026-10-07
- **Relates to:** README "Analytics", "Submodel template conformance"; ADR 0001

## Context

Real corpora repeat ids. A vendor ships the same ContactInformation submodel, with the
same id, in every one of thousands of files (an **identical repeat**). Other files reuse
placeholder ids such as `https://example.com/ids/sm/0001` for submodels that are actually
different (an **id collision**). In Neo4j an Identifiable (AAS, Submodel,
ConceptDescription) is one node per id, so the import has to decide what happens on the
second occurrence. That choice decides what every count in the report means.

**What neo4aas master does** (verified against `rwth-iat/neo4aas` master `2fdd26b`):
Identifiables are merged by `id`. The first occurrence (in sorted file order) wins, and
every later one is dropped with its whole subtree before anything is written. Only an
info log line (`Skipped N duplicate Identifiable(s)`) remains. How often an id occurred,
the content of every later occurrence, and whether a repeat was identical or a collision
cannot be recovered afterward.

**How references become links** (same commit): the upload stores each Reference as a
node, merged with identical References by a hash of their content. It does not link
anything. A separate call, `resolve_references()`, deletes every `:references` edge and
rebuilds all of them by looking up `Identifiable {id: keys_value[0]}`. Any id that
exists on two nodes at that moment gets linked to both.

**Turning the merge off is not an option on its own.** With `deduplicated_by_id` emptied,
the `identifiable_id` UNIQUE constraint aborts the whole batch on the first repeat.
Dropping the constraint as well puts both variants of a collision under one id, and
`resolve_references()` then links every reference to that id to both: the AAS of one
file appears to own the other file's submodel.

## Decision

Identical repeats are merged, as master does. Each collision variant is kept as its own
node with the original id, linked only from its own file. AASpect does this in four steps
around the neo4aas upload:

1. **Scan.** While reading the files, AASpect hashes each Identifiable's content and
   records, per id, every occurrence and every distinct content.
2. **Rename.** The first content (in sorted file order) keeps its id. Every later
   distinct content is renamed to `<id>__collision-<n>`, with `n` counted upward until
   the name is used by no id in the corpus. Every Reference in the same file whose first
   key is that id is rewritten to the new name. Identical repeats are left alone; master
   merges them.
3. **Upload and link.** AASpect uploads the rewritten environments via `upload_xml(env)`
   / `upload_json(env)`, then calls `resolve_references()` once. Every id is unique at
   this point, so each reference links to the variant from its own file.
4. **Restore.** Each renamed node gets its original `id` back and a `collision_index`
   property set to `n`. On each rewritten Reference node, `keys_value[0]`, `target_id`
   and `target_id_base` get the original id back.

Step 4 leaves several nodes with one id, so it needs neo4aas to skip the
`identifiable_id` UNIQUE constraint. This becomes a config option in neo4aas, contributed
upstream. *Amended by ADR 0008:* on PostgreSQL AASpect defines the tables and sets no such
constraint, and linking and restore are AASpect's own SQL; the restrictions below still hold.
neo4aas's mapping still needs the option (`enforce_unique_ids=False` in the PostgreSQL
writer), so AASpect pins the fork of neo4aas that has it until upstream merges it
(rwth-iat/neo4aas#36).

The report states counts as "distinct contents" and lists, per Identifiable, how many
files it occurred in. Each collision is listed as a data-quality finding.

### Restrictions this places on AASpect

- **One corpus, one import.** Steps 1 to 4 run over the complete corpus in one go.
  Files are never added to an existing graph; a changed corpus is imported from scratch.
  Batching inside one import is fine, because the restore runs after the last batch.
- **Links are built exactly once, before the restore.** Nothing may call
  `resolve_references()` or `resolve_references_for()` afterward. In neo4aas these are
  also called by the ECLASS ingest (`eclass/ingest.py`), the BaSyx server backend and
  `Neo4jObjectStore` writes, so none of those may run against an AASpect graph after the
  restore.
- **No query selects an Identifiable by id alone.** After the restore, an id can match
  several nodes. Queries reach an Identifiable by following existing `:references`
  edges, or filter on `collision_index`. This applies, for example, to template
  extraction, which currently selects by `s.id IN $ids`.
- **AASpect owns file reading for the upload.** It cannot use neo4aas's
  `upload_all_*_from_dir`, because the environments must be rewritten before upload.

## Consequences

**Good:** No content is lost: every collision variant is stored and analyzed, and each
AAS links to its own submodel. Counts are not skewed by whoever copies the most,
because identical repeats are still one node. Ids in the graph and in the report are the
ids from the files. The scan has no I/O, so it can be tested without Neo4j. AASpect must
read every file anyway, for schema validation and because uploads are untrusted input.

**Bad:** Correctness depends on order (link, then restore) and on nothing relinking
afterward; the restrictions above are rules that code review has to enforce, not
something the graph guarantees. A Reference from *another* file to a colliding id links
only to the first variant; which variant it meant cannot be known, so the report can
only point at the collision. After the restore, two Reference nodes can have identical
content and a stale stored `hash`; harmless because the constraint checks read the keys
of each node and no later import merges against them. The hash covers the whole content,
so a newer revision of a submodel, or reordered language strings, counts as a collision.
The report must say "different content under one id", not "error". Occurrence counts are
attached per Identifiable only; weighting element-level statistics by occurrence would
make queries considerably more complex.

**Neutral:** Counts mean "distinct contents", not "files". The report says so in its
overview. The approach needs a neo4aas option that does not exist on master yet.

## Alternatives considered

| Option | Why not |
|---|---|
| Master as-is (merge by id) | Collision variants vanish without notice, and the AAS of the second file links to the wrong submodel. |
| Rename every repeat, identical ones too | One widely copied submodel dominates every distribution; one mistake becomes N findings. |
| Master merge plus scan, no rename | Collisions are reported, but the second variant is never analyzed. |
| Rename collisions and keep the temporary ids (no restore) | Needs no upstream change, but ids in the graph and report differ from the files. Kept as the fallback if the upstream option is not accepted. |
| Name variants by content hash instead of a counter | Also works; a counter checked against all corpus ids is shorter and equally collision-free. |
| Link references to every node with the id, and flag it in the report | Leaves known-wrong numbers in every statistic that touches a colliding id. |

## Revisit when

- The upstream option to skip the uniqueness constraint is rejected: switch to the
  no-restore fallback above.
- Adding files to an existing corpus becomes a requirement: the one-import restriction
  no longer holds.
- A real corpus shows how many "collisions" are only revisions. If most are, decide
  whether the hash should ignore order or version fields.
- neo4aas gains a supported way to link references within their own file, which would
  make the rename and restore unnecessary.
