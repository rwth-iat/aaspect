# 0007. Download the IDTA submodel templates at runtime and match by semanticId

- **Status:** provisional — pending verification
- **Date:** 2026-10-22
- **Relates to:** README "Submodel template conformance", "Analytics"; ADR 0001, 0002,
  0003, 0004

## Context

Template conformance checks each submodel of a corpus against the IDTA submodel template
its semanticId names: are the mandatory elements there, how often does each occur, do
element and value types match. Analytics needs the same templates to tell IDTA-standard
submodels from others: going by the identifier alone counted Handover Documentation,
whose semanticId is an ECLASS IRDI, as ECLASS.

The templates are IDTA's. Their repository
([admin-shell-io/submodel-templates](https://github.com/admin-shell-io/submodel-templates))
is under CC BY 4.0, but its `published/` folder adds "Different copyrights and
intellectual property might apply. See SMT specifications." AASpect will be hosted
publicly, and the project downloads such third-party material at runtime rather than
shipping it. The repository is 180 MB; the template JSON files AASpect
needs are about 36 MB.

The repository holds every edition: `published/<template>/<major>/<minor>[/<patch>]/`
with a JSON per metamodel serialization (V3.0, V3.1), samples and examples beside them,
and `deprecated/` for deprecated ones. Patch editions share their semanticId; major
editions usually change it, but not always in a way that survives normalization:
Handover Documentation 1.2 and 2.0 differ only in the IRDI version (`#001`, `#003`).

What the reference implementation (an earlier prototype, ported to a neo4aas
branch) did, and what AASpect keeps: templates are read from files,
never put into the graph; instances are read from the graph with one extraction query per
chunk of submodels; all rules run in Python (ADR 0001). The reference shipped no
templates at all; each user had to download them.

## Decision

**Source.** AASpect downloads the templates at runtime from one pinned commit of IDTA's
repository, over GitHub's raw file server or a mirror (`AASPECT_DOWNLOAD_URL`, shared with the schemas of ADR 0004), and keeps
them in memory. `src/aaspect/adapters/templates/manifest.json` lists the files: path, git
blob hash, edition and tier, nothing of their content. Each download is checked against
its hash, so neither a mirror nor a changed repository can change what is checked.
`tools/template_manifest.py <commit>` writes a new manifest; moving to newer templates is a
reviewed change. Download starts with the server and is retried at most every five
minutes; until it succeeds, the template section fails with a plain reason and analytics
falls back to the identifier.

**Which files.** Per edition folder one file per template: the V3.1 serialization where
there is one, never samples or examples. The newest edition of each template is
*current*, the others *superseded*, those in `deprecated/` *deprecated*. A template without
a semanticId is found by its submodel id (IDTA ships some that way).

**Lookup.** A submodel's exact semanticId (trimmed) first, then the semanticId without its
IRDI version and without whitespace. Among templates found, uploaded before current before superseded before
deprecated, newest edition first. The report names the template and its tier for every
result.

**Which edition.** The edition is read from the folder path, never from the file name,
which also carries part numbers (IDTA 02035-3 is part 3 of the Battery Passport). A
template nested in another family (the Battery Passport parts) is a profile: where it
shares a semanticId with a template of its own, such as Carbon Footprint, that one is
preferred. Files without a submodel are left out of the manifest.

**Matching inside a submodel.** In passes, each on what is left: a template element's own
semanticId, ignoring IRDI versions in every part of a composite id, an ECLASS `*01`
suffix and whitespace, which is never part of an id but occurs inside template ids; then, where the template element has no semanticId or siblings share one, the
exact idShort, then an idShort fitting a placeholder (`{00}`, `__00__`) or numbering
(`ProductImage01` for `ProductImage`); then alternatives sharing a semanticId by element
type; last, wildcard elements (idShort containing `arbitrary`, or ids such as
`NON_EMPTY_VALUE`) take the remaining elements of their type, checked for their count
only. A list item is compared with the item template of its semanticId, else of its
type, else the one it deviates least from. Alternatives sharing a semanticId (the
interface kinds of Asset Interfaces Description, each 1..*) are counted together: one of
them is enough. A key carried by wildcards too is never a concrete element's own, so an
element of a wildcard's type goes to the wildcard.
Collections, lists (each item against the template's item) and entity statements are
compared level by level, up to 64 levels. Errors: missing mandatory element, cardinality,
element type, value type of Properties and Ranges. Notes: undefined elements, other
idShort, other semanticId version. Only an IRDI version counts as another version: an
`*01` suffix the instance leaves out does not.

**Cardinality.** IDTA's guideline "How to write a SMT" (v1.1, §9.2) defines
`SMT/Cardinality` (legacy `Multiplicity`) as how many instances of an element "are
allowed in the actual collection (hierarchy level of the Submodel)", with the values
`One`, `ZeroToOne`, `ZeroToMany` and `OneToMany`. The qualifier is read by the last
segment of its type and its value ignoring case and surrounding spaces, as IDTA's
templates also write `SMT/SMT/Cardinality`, `ZerotoOne` and `ZeroToOne `; the
off-guideline values `TwoToMany` and `Three` are read as 2..* and 3..3. For a list item
the hierarchy level is the list, so the item's cardinality bounds how many items the
list holds. All item templates of a list are counted together, whatever their
semanticIds: the items of one list share theirs (AASd-114), so requiring each would never
be met. An item whose upper bound is 1 (`One`, `ZeroToOne`) sets only its lower bound:
templates mark lists that hold several items that way (Carbon Footprint's
`LifeCyclePhases`, Plastic Waste's `MeasuredValues`).

## Consequences

**Good:** The public instance checks conformance out of the box, without redistributing
IDTA files. Results are reproducible: the same commit, the same hashes. Analytics and the
conformance check use one catalogue, so they never disagree on which template a submodel
follows. Rules are tested without network or database.

**Bad:** The server needs outbound HTTPS to GitHub (or a mirror) and about 36 MB per
start; an offline deployment gets no template conformance until a mirror is set up. New
IDTA editions arrive only with a new manifest. The edition and tier are read from folder
and file names, a convention IDTA does not promise; a renamed folder shows up as a changed
manifest when it is regenerated. IDTA's own templates contain mistakes (Handover
Documentation 1.2 declares `DigitalFile` a collection), and AASpect reports deviations
from them faithfully. Ignoring IRDI versions at element level can match an element to a
template element whose meaning changed between versions; it is reported as a note.

Template elements without a cardinality qualifier are not counted: the SMT guideline
v1.1 defines no default, and IDTA's own current templates leave 379 elements without
one. Reading an item's upper bound of 1 as none misses a list that really should hold
one item; the benchmark corpus (2,626 JSON files) has no list where the two readings differ.

Template conformance cannot be turned off on its own: with a graph database the
templates are always downloaded (once per start; a retry fetches only files that failed),
each file within 60 s.

**Neutral:** Counts follow ADR 0002: a submodel repeated identically in many files is
checked once and located in its first file. Uploaded templates (README) are the highest
tier, read per analysis through a reader with its own budget, and bounded at compile time
(5,000 elements, 1,000 siblings, 16 list item kinds, idShorts of 128 characters); each
submodel's comparison has a work budget and checks the deadline, since uploaded templates
are untrusted.

## Alternatives considered

| Option | Why not |
|---|---|
| Copy the templates into the repository (as ADR 0004 first did for the schemas) | Redistributes IDTA material under terms not fully known; the project does not ship third-party files. |
| Download at image build time | The published image still contains the files; same license question, only moved. |
| Operator supplies a template folder (the reference's way) | A fresh install checks nothing; every operator must find and curate the right editions. |
| Download the whole repository archive | 180 MB per start for 36 MB of templates. |
| Ask GitHub's API for the file list at startup | Rate-limited without a token, and the list would follow the repository instead of a reviewed pin. |
| Put templates into the graph and match in Cypher | ADR 0001: the graph holds only the corpus; rules stay in Python. |

## Revisit when

- The license question is settled for good: if shipping is fine, a copy would remove the
  network dependency.
- IDTA changes its folder layout, or a regenerated manifest shows tiers that look wrong.
- Real corpora show many element matches across IRDI versions with different meaning, or
  many false "unexpected element" notes: then reconsider version-free matching or the
  idShort fallback.
  *Checked 2026-11-12 on per-vendor-500 (2,626 JSON files):* 88,092 of 94,100 version
  notes only differed by the `*01` suffix, and 23,860 unexpected-element notes came from
  whitespace inside template ids (Handover Documentation 1.2's `PreviewFile`, Contact
  Information). Both fixed; findings fell from 204,649 to 114,080. The matched
  `PreviewFile`s now give model-type errors, as Handover Documentation 1.2 declares it a
  collection, like `DigitalFile`.
- ~~The schema files (ADR 0004) move to runtime download too; both should share one
  download mechanism.~~ Done 2026-10-22: both use one pinned download and
  `AASPECT_DOWNLOAD_URL`.
