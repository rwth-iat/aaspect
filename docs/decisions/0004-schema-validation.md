# 0004. Validate against copied official schemas, version detected per file

- **Status:** provisional — pending verification
- **Date:** 2026-10-07
- **Relates to:** README "Schema check"; ADR 0001, ADR 0003

## Context

The schema check validates every uploaded file against the official AAS JSON schema or
XSD for metamodel V3.0, V3.1 or V3.2. Four things had to be settled:

**Where the schemas come from.** They are published in `admin-shell-io/aas-specs-metamodel`
under `schemas/` (3.2 on master, older versions in older releases). The same folder also
holds RDF schemas (OWL ontology, SHACL shapes). They only matter for AAS serialized as
RDF, which the README does not plan for.

**Which version a file uses.** A corpus mixes vendors and years, so 3.0, 3.1 and 3.2
files sit side by side. In XML the namespace names the version exactly (verified). JSON
carries no marker, so its version can only be learned by validating it.
Running every file against all three versions triples the cost. Giving the whole corpus
one version marks every file from another version as heavily invalid. The report then
drowns in errors that only mean "wrong version".

**Speed.** An earlier prototype ran JSON validation in Node.js (ajv) for speed. Test
setup (2026-10-07): Docker `python:3.12-slim`, the official 3.2 `aas.json`, synthetic
valid documents, one core.

| Document | `jsonschema-rs` 0.58.6 | `jsonschema` 4.26.0 |
|---|---|---|
| 0.3 MB | 0.6 ms | 4.6 s |
| 5.2 MB | 13 ms | 88 s |
| 25.9 MB | 70 ms | 441 s |

At about 17 s per MB, pure-Python `jsonschema` is unusable for a corpus, even when
spread across all cores.

**A correctness trap (verified 2026-10-07).** The 3.2 schema (draft 2019-09) writes one
string pattern, used 38 times, as UTF-16 surrogate pairs (`\ud800[\udc00-\udfff]`).
`jsonschema-rs` refuses to compile it (`is not a "regex"`). Python `jsonschema` compiles
it but rejects every string containing an emoji or another character outside the BMP.
Rewritten as `\U00010000-\U0010ffff`, the pattern works correctly in both libraries.

**Platform.** The `jsonschema-rs` wheel aborts the process on a Windows development
machine because a CPU feature is missing (no fix upstream). It runs on Linux in Docker.

## Decision

- **Schemas** for JSON and XML, V3.0, V3.1 and V3.2, are downloaded at startup from
  IDTA's aas-specs-metamodel repository, pinned to one commit per version and checked by
  size and SHA-256 (amended 2026-10-22; first they were copied into the repository). The
  project does not redistribute third-party material with AASpect. The
  server serves nothing until the schemas have arrived and retries with pauses growing
  from 30 s to 15 min; a mirror can be set with `AASPECT_DOWNLOAD_URL`, a proxy with
  `HTTPS_PROXY`. Neither schema may refer to another document. RDF schemas are not used.
- **Everything version-specific in one file** (added 2026-10-22): `domain/metamodel.py`
  holds the version names, XML namespaces and pinned schemas. A new version is added
  there; adapters derive what they need from it.
- **Libraries:** `jsonschema-rs` for JSON, `lxml` (libxml2) for XSD.
- **Patterns:** when the schemas are loaded, the surrogate-pair pattern is rewritten to
  the code-point range. Loading fails if any surrogate escape remains, so a schema update
  that introduces a new form fails loudly. A test pins the behaviour for emoji, CJK-B
  characters, control characters and lone surrogates.
- **Element types are chosen by `modelType`** (added 2026-10-07). The schemas' `oneOf`
  over element types is rewritten on load into an if/then per `modelType`, with
  `modelType` required and unknown types rejected. Listing all errors of the original
  `oneOf` grows exponentially with nesting: one real 0.5 MB vendor file needed
  more than 14 GB, and jsonschema-rs aborts the process when an allocation fails. The
  same approach (ajv's `discriminator`) was used in the earlier prototype; jsonschema-rs
  lacks that keyword, so it is expressed in standard keywords. Verdicts were compared
  against the original schema on the official examples (0 of 23,958 changed); the
  full-corpus comparison is in the benchmark below. A `oneOf` of any other shape fails
  loading. Validation first asks `is_valid` and lists errors only for invalid files.
- **Validation runs in isolated worker processes** (added 2026-10-07) with a time and a
  memory limit; a worker over either is killed and replaced, and the file gets a
  `validation-timeout` / `validation-aborted` violation. Reason: libxml2's pattern
  matching grows ~8× per doubling of a failing value's length (1,600 characters: 30 s),
  and jsonschema-rs aborts the process on a failed allocation. Neither is interruptible
  from Python. Documents are validated in parallel through these workers.
- **Limits on one analysis** (added 2026-10-07, after the security review): at most
  1,000 violations per document and version, plus a note; at most 10 minutes per
  analysis, after which remaining documents are "not checked"; at most 1 GB of document
  data and 100 AAS parts per package. All configurable via `AASPECT_*`.
- **File-level problems end the version search** (added 2026-10-07): a malformed file, a
  timeout or a crashed worker says nothing about any version, so auto mode stops at the
  first such result and reports the version as "not determined".
- **Lone surrogates.** A file can contain one (`"\ud800"` is legal JSON) and
  `jsonschema-rs` raises an exception on it. The adapter catches that and reports it as
  a violation, never as a crash.
- **Grouping** uses the rule path: the schema location for JSON; for XML, where libxml2
  names no rule, the error type plus the element and its parent (amended 2026-10-07; the
  full element path split one rule per nesting depth). Messages are not used for grouping, because a
  `oneOf` message includes the whole failing element. Messages are truncated.
- **Version is decided per file, never per corpus:**
  - XML: the namespace decides. The user's version choice does not apply to XML.
  - JSON with a version chosen by the user: one run against that version.
  - JSON on auto: oldest version first, stopping at the first that passes. The file is
    reported as "valid as X; newer versions not checked". A second auto mode tries the
    newest version first instead (amended 2026-10-15; before, newest first was the only
    auto mode).
  - JSON that passes no version: every version is run, and the violations of the version
    with the fewest are reported. If two versions tie, the one tried first wins: the
    older one by default, the newer one in the newest-first mode.
- The report summary shows the version distribution across the corpus.

## Consequences

**Good:** JSON validation is about 6000× faster than in pure Python, so auto-detection
across three versions is affordable. Mixed corpora are reported without false "wrong
version" errors. Validation is reproducible, since each schema is pinned by commit and
hash, and schema updates show up as diffs of those pins.
The validator sits behind the `SchemaValidator` port, so replacing it touches one adapter.

**Bad:** **The JSON adapter could not run on a Windows development machine.** Any test run
that imported it there was aborted entirely, not merely failed. Develop and test on Linux. The project depends on a Rust binary
wheel for every target platform. AASpect does not validate against the official schema
byte for byte; the pattern rewrite has to be re-checked on every schema update. Auto mode
costs up to three runs for every JSON file that is invalid. "Valid as 3.2" does not say
whether the file is also valid as 3.1. "Fewest violations" is a crude measure of
closeness. Pinned schemas go stale until someone moves the pins. The server needs
outbound HTTPS (or a mirror) at startup and serves nothing until the download succeeds.

**Neutral:** Later analyses that need one version per file (template conformance, the
neo4aas import) can reuse this result, but they need their own tie-breaker if a file is
valid under several versions.

**Open for the constraint check** (added 2026-10-07): the neo4aas constraint checker runs
over the whole graph with one rule set, so it cannot follow the per-file version. In a
mixed corpus, files of other versions are judged by the wrong rules (AASd-002 differs in
V3.0, AASd-090/120 exist only in V3.0, AASd-137/138 only in V3.2). The per-file versions
found here are the input for choosing that one version (user's choice or most common)
and for naming the files whose constraint results may be wrong. The choice itself is
decided with the constraint check, after ADR 0002.

**Decided for the constraint check** (2026-10-15): one version for the whole corpus, the
one chosen by the user, else the most common among the imported documents (the older
on a tie). The report names the files determined as another version, or none, as
possibly judged wrongly. A sample of 40 files from each real vendor corpus showed one
version per vendor under oldest-first detection; mixing comes from uploading several
vendors together. Rejected: one database per version (analytics would have to query and
add up several graphs) and one checker run per version filtered to each file's version
(up to three runs, for a case that real corpora rarely show).

## Alternatives considered

| Option | Why not |
|---|---|
| Python `jsonschema` | About 6000× slower; 7 minutes for a single 26 MB file. |
| Node.js + ajv via subprocess | Proven in the earlier prototype, but needs a second runtime and a process boundary. `jsonschema-rs` is fast enough without either. |
| fastjsonschema | Supports drafts 4/6/7 only. The schema is 2019-09. |
| `xmlschema` (pure Python) for XSD | Much slower than libxml2, with no gain in correctness. |
| One version for the whole corpus | Files from other versions drown the report in "wrong version" errors. |
| Always validate all versions | Costs three times as much, even when the user knows the version. |
| Copy the schemas into the repository (the first decision) | Redistributes IDTA material; the project does not ship third-party files. Offline startup would be its gain. |
| Fetch whatever the repository holds at runtime, unpinned | Results not reproducible, and the schema source becomes an input nobody checks; pinning by commit and hash avoids both. |

## Revisit when

- ~~A real corpus has been validated. The benchmark above used synthetic documents only.~~
  Done 2026-10-07 on 11 non-public vendor corpora plus IDTA templates: 244,113 files,
  111.6 GB, 0 crashes, 33.6 min of single-core work (median 2 ms per file, p99 36 ms),
  peak memory 116 MB. The modelType dispatch changed none of 551,190 valid/invalid
  verdicts. 2,000 JSON files: 10.8 s isolated with 1 worker, 2.2 s with 8.
- ~~The 3.0 or 3.1 schemas turn out to use pattern forms other than the 3.2 one.~~
  Checked 2026-10-07: all three JSON schemas (3.0.9, 3.1.2, 3.2.0) use the same single
  surrogate pattern, and the rewrite makes all of them compile.
- Observed 2026-10-07 with the official generated examples: JSON files written for 3.0 or
  3.1 are also valid as 3.2. Newest-first auto mode therefore labels them "3.2", which is
  why oldest first became the default (2026-10-15). For the schema check either is
  correct; any analysis that needs the version a file was *written* for (e.g. the
  constraint check) cannot rely on the auto-detected JSON version.
- `jsonschema-rs` publishes a Windows wheel that runs on that machine, or stops
  publishing Linux wheels.
- An RDF-serialized corpus appears. Add a SHACL adapter.
- Users ask "which versions is this file valid under?" Then auto mode should run all
  versions.
