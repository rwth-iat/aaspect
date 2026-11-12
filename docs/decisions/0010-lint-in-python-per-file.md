# 0010. Lint ids and modelling leftovers in Python, one file at a time

- **Status:** accepted (2026-11-12, after timing it on the benchmark sets)
- **Date:** 2026-11-12
- **Relates to:** README "Features"; ADR 0001, ADR 0002, ADR 0003, ADR 0008

## Context

Many AAS files are valid against the schema and the metamodel constraints and still hard
to use. An id carries a trailing space or a zero-width character, so it never compares
equal to the id another file uses for the same thing. A submodel keeps the id of the IDTA
template it was copied from, so every vendor who did the same now shares one id. Files
still carry `category`, or the cardinality qualifiers of older template guidelines. A
reference names an element that does not exist in the file it comes from.

Miny et al., "Automatic Quality Assessment of Asset Administration Shell Submodel
Templates", describe such checks for templates. AASpect analyses uploaded instance files,
so it adopts the checks that apply to instances (whitespace, deprecations, dangling
references) and adds checks on ids the paper does not cover. Checks that only make sense
on templates (how cardinality is modelled, qualifier kinds, conflicting re-definitions,
arbitrary content) are left out. So is the paper's singular/plural idShort check: it needs
an English-only inflection library and can only guess.

Where the checks run matters for one of them. The graph stores an object that occurs
identically in many files only once (ADR 0002), so it cannot answer "does this reference
lead anywhere *in its own file*". The parsed environment of one file can. The other
checks are rules on single values: a pattern, or a look-up in a set of ids.

## Decision

The linter is a fifth analysis with its own report section. Its rules run in Python, in
`domain`, on the environment (AAS JSON structure) of each file. The import already parses
every document once to scan its ids; the linter is fed the same environment there, so no
file is parsed again. Checks that compare files (near-identical ids, ids taken from
templates) collect what they need while the files go by and decide at the end.

Severity says what the problem breaks:

- **error:** lookups or automatic processing fail. Leading or trailing whitespace, or an
  invisible character, in an id or a reference key; a reference whose target should be
  in its own file but is not.
- **warning:** allowed by the metamodel, but very likely a mistake. An id with whitespace
  inside (it still equals itself), or one that looks like an IRI, IRDI, URN or UUID but
  is broken; an id copied from a template or on an example host; ids that differ only in
  case or a trailing slash; a `globalAssetId` equal to its shell's id; deprecated
  cardinality qualifiers; template qualifiers in an instance.
- **info:** deprecated but harmless. `category`.

A reference whose first key names an object that is not in the same file is not
reported: the target may sit in another file, or outside the corpus. An id a reference
names is judged where the corpus defines it, and only at the reference if the corpus
does not. Nothing another analysis reports is repeated: id collisions (including one id
for objects of different kinds) stay with ADR 0002, whitespace in language tags with the
schema check, and template qualifiers of kind `TemplateQualifier` with the metamodel
constraints. Findings are located and grouped as in ADR 0003: by file and idShort path,
an object in many files listed once with its file count, and a cap on the places kept
per check. Paths and values from the file are cut when an issue is made, not when it is
shown, so a crafted file cannot make the linter slow or large.

The linter sees every document the import can read, including those the database later
refuses; documents the import cannot read are not linted, and the section says so. A
failure of the linter on one document is logged and named, and the next one linted.

## Consequences

**Good:** The rules are testable without a database, like every other rule in `domain`
(ADR 0001). The dangling-reference check is exact per file. No extra parse, no new port,
and no adapter change: the report page, JSON and PDF show any section.

**Bad:** The import's id scan now also feeds the linter, so `import_corpus` has a second
caller-supplied concern. Linting adds one more walk over every environment in the
worker, about 8 % of the import (see Evidence). An object repeated identically in many files is
walked once per file, where the graph would hold it once. The linter needs the
environment parser, so like the graph-based analyses it only runs when a graph database
is configured. Ids are compared on their first 256 characters (as in analytics), so two
longer ids that differ only after that are treated as one.

**Neutral:** This does not touch ADR 0008, which decides that the *metamodel constraint*
checks run as SQL. Template ids come from the catalogue template conformance already
loads; without templates, the copied-template-id check is skipped and the section says so.

## Alternatives considered

| Option | Why not |
|---|---|
| SQL on the graph, like the constraint checks | Identical objects are merged across files, so "in its own file" cannot be asked; the other checks gain nothing from the database. |
| Parse every file a third time, in a separate pass | Parsing is the most expensive step of the import; the scan already holds the environment. |
| Lint templates instead of the corpus (as the paper does) | Helps template authors, not the people uploading files; most findings would blame them for template flaws. |
| Report malformed ids as errors | The metamodel allows any string as an id; such an id still works as a key. |

## Evidence

**Cost (2026-11-12, native Linux, one process, in-process timing of the scan pass).**

| Set | Files | Parse | Id scan | Lint |
|---|---|---|---|---|
| per-vendor-100 | 1,026 | 4.7 s | 1.5 s | 4.7 s |
| per-vendor-500 | 4,626 | 20.4 s | 6.5 s | 20.2 s |

The first version took 7.5 s on per-vendor-100: the id and the dangling-reference checks
each searched every element for References, down into every key. Searching once per
element and never into keys gave 4.3 s; judging referenced ids and every Unicode
format character brought it back to 4.7 s. The PostgreSQL upload of per-vendor-500 takes
226 s (ADR 0008), so lint adds about 9 %. Through the web app, with PostgreSQL,
per-vendor-100 finished every section in 87 s, upload included.

**Crafted files (security review, 2026-11-12).** Before paths were cut while being built,
a 4 MB file of nested reference chains took 143 s to lint and an 810 KB file of deep
collections kept 478 MB; both now take 0.01 s and keep one 512-character path.

**What it finds (per-vendor-100).** Surrounding whitespace or invisible characters in
ids or keys: 407, among them IRDIs with a trailing space. Malformed ids: 1,091, among
them an official ZVEI semanticId with a space inside its path and IEC 62720 unit IRDIs
without a version, which IDTA's own templates use; if those prove to be the norm rather
than a mistake, exempt them. Submodels keeping a template's id: 226 (through the web app,
with the IDTA templates). Ids on example hosts: 4,294, mostly semanticIds copied from
tool defaults. Ids differing only in case or a trailing slash: 428. `category`: 352,338,
old cardinality qualifiers: 10,942, template qualifiers outside templates and without
the `TemplateQualifier` kind: 847. No dangling references.

## Revisit when

- The linter adds more than a tenth to the import time on a real corpus: look at walking
  an object once per content instead of once per file.
- A check needs relations across files that the environments alone cannot answer
  cheaply: then that check moves to SQL on the graph.
