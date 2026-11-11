# 0003. One generic report shape for every analysis

- **Status:** provisional — pending verification
- **Date:** 2026-10-07
- **Relates to:** README "Planned features" (web UI, JSON/PDF download, all analyses); ADR 0001, ADR 0002

## Context

AASpect will run four kinds of analysis: schema check, metamodel constraints, analytics
and template conformance. They are built one after another, and the web UI is built
alongside the first one (the schema check) instead of after all of them. Each later
analysis should then plug in without touching the UI, the JSON export or the PDF export.
That works only if every analysis returns results in one shape that those three outputs
can render without knowing which analysis produced them.

The analyses produce two different kinds of result:

- **Problems**, one per broken rule: a schema violation, a failed `AASd-xxx` constraint,
  a missing mandatory template element. The same problem often recurs. The README asks
  for recurring schema violations to be grouped, and ADR 0002 reports one finding as
  "affects 4 files".
- **Counts**: which submodels, semanticIds, element types and valueTypes occur, and how
  often. Listing 500 semanticIds as 500 "problems" would make no sense.

**Assumption, not verified:** these two kinds cover every planned analysis. This has been
checked against the README only, not against a working analytics or template-conformance
implementation.

## Decision

A `Report` holds corpus metadata (uploaded files, AASpect version, the "distinct objects"
counting rule from ADR 0002, format version) and one **section** per analysis. Each
section has a stable key (e.g. `schema`) for JSON consumers, a title, a status
(`completed`, `failed` with a reason, or `skipped`) and a list of blocks of exactly two
kinds:

- **Finding**: rule id (`AASd-119`, a schema keyword, a template rule), severity
  (`error` / `warning` / `info`), message, and **all** of its locations. A location is
  the file, the Identifiable id and the element path. Each field is optional, because
  graph-based checks cannot always name a single file (ADR 0002).
- **Table**: title, column names, rows of plain values (text or number). Distributions
  are two-column tables.

**Steps report while they run** (amended 2026-10-14). A section can also be `waiting`
or `running`, with no blocks yet, and a report is `finished` once no section is either.
The web page shows a report as soon as an analysis starts and polls until it is finished,
because a graph import takes minutes. The JSON download carries `finished` (format
version 2). Since ADR 0009 (2026-11-04), downloads are offered for finished reports
only, so the field is always true there; progress comes from `/status`. It stays for a
stable format.

**Metamodel versions are not report metadata** (amended 2026-10-07). They are a result of
the schema check, so its section shows them as two tables: the distribution across the
corpus and the version of each file. A later analysis that needs them, such as the
constraint check, gets them from the schema check inside the app layer, not from the
report. It states in its own section which version it used.

**Objects shared by many files are located once** (amended 2026-10-15). An identical
repeat is one node (ADR 0002), so a constraint violation inside it belongs to every file
holding it, which can be tens of thousands. Its location names the object id, the
element path and the first of those files; the finding's message gives the number of
files. Listing every file would make one violation in a widely copied submodel weigh
megabytes of JSON.

**Blocks and sections say what the renderer used to guess** (amended 2026-10-25). The
web UI builds a summary, a page per uploaded file and charts. It inferred all three
from content: a cell looking like `file.aasx:/part` was a file, a column named
`Share (%)` was a distribution, a file with no listed error passed. Uploaded content
can look like a file name, so a crafted id put rows on another file's page. A renamed
column silently changed a chart. A violation in an object shared by many files names
only the first (see above), so the other files showed as passing. An analysis skipped
because no database is set up counted as unfinished, so the verdict never turned
green. The analysis knows each of these facts, so it states them:

- A table may name its **file column**: the position of the column holding document
  labels. Only that column links to file pages and decides which rows a file page
  shows. A table without one is corpus-wide and stays off file pages.
- A table has a **kind**: `plain`; `shares` (last two columns are a count and its
  percentage of a whole); `coverage` (last three are filled, of and percentage, each
  row its own whole); `conformance` (the first two number columns are a total and how
  many of it conform). Renderers may still choose a layout from the shape, such as key
  figures for a one-row table.
- A section states whether its error findings **name every file** they affect. It
  defaults to no: a pass is claimed only where an analysis guarantees it.
- A section switched off by configuration has the status `not_configured`. It does not
  hold the report's verdict back the way a failed or timed-out section does.

The JSON download carries all four (format version 3).

The types are pure dataclasses in `domain`. JSON, HTML and PDF are produced from them by
adapters. A third block kind needs a change to this ADR.

## Consequences

**Good:** A new analysis only adds a section. The UI, JSON and PDF stay unchanged. If an
analysis seems to need its own screen, that shows the domain type is missing something
and should be fixed there. A failed analysis, such as Neo4j being unreachable, gives a
failed section and the rest of the report still arrives. Grouping repeated problems into
one finding keeps reports readable at 100+ files. Analysis logic can be tested by
comparing plain dataclasses.

**Bad:** A generic renderer gives no tailored views, such as a template tree with the
missing elements highlighted. Charts come from a few table kinds; a new kind of chart
needs a new kind here, which is a format change. Every analysis must set its file
column and its "names every file" flag; forgetting either hides results from file
pages or softens the verdict, but never claims too much. Every text field
can carry content from uploaded files (idShorts, descriptions, ids), so **every renderer
must escape every field** (hard rule 3). There is no "trusted" field to rely on. The JSON
export becomes an external format: once people download it, changing it needs a new
format version. For a large corpus with one finding that occurs very often, the location
list grows without limit. The UI will have to truncate it; the JSON will not.

**Neutral:** Severity is chosen by each analysis. Following ADR 0002, an id collision is a
`warning`, not an `error`.

## Alternatives considered

| Option | Why not |
|---|---|
| A result type and UI view per analysis | Every new analysis touches the UI, JSON and PDF. This is the rework the incremental UI should avoid. |
| Findings only, with analytics as `info` findings | Distributions become hundreds of unreadable entries. |
| SARIF (standard format for static-analysis results) | Built around source files and line numbers, which mean nothing inside an AASX package. It has no place for statistics, and it is verbose. It can still be added later as an extra export produced from these types. |
| Free-form dict / JSON | No types to check against. The renderer would have to guess the structure. |
| Keep inferring meaning from content and fix the column names as a contract | Uploaded content still decides which file page a row lands on, and renaming a column still breaks a chart without any failing test. |
| Chart types (bars, stacked bar) on tables | Puts the web page's layout into the domain; the PDF may draw the same kind differently. |

## Revisit when

- Analytics or template conformance is implemented and needs something that is neither a
  finding nor a table. Extend this ADR or supersede it.
  *Analytics, 2026-10-22: fits without a change.* Every result is a table (distributions,
  rankings capped at 100 rows, spreads); steps not computed within the time limit or
  failed are warnings. Charts would still have to be inferred from the tables.
- A real 100-file corpus produces a report whose JSON or UI is impractical to use (size,
  load time, number of locations). Then decide whether to cap or page locations.
- Findings need grouping. Id collisions give one finding per content, so an id with
  nine contents gives nine findings in a row; grouping them by id was asked for on
  2026-10-14 and deferred. Preferred shape then: an optional `group` label on a finding,
  rendered as one foldable box per group, rather than a third block kind.
- ADR 0002 is decided. Check that its counting rule and the collision severity match the
  report metadata.
