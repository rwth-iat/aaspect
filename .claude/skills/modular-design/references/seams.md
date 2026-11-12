# Picking a seam in this project

A seam is where you can replace one side without the other noticing. Put them where change is *likely*, not everywhere — a port that will only ever have one implementation and no test double is just noise.

## Candidate seams, and why

None of these exist yet. They follow from the planned features in `README.md`; names are proposals. Confirm (or reject) each one when the first feature that needs it is built, and record the choice as an ADR.

| Port (proposed) | Separates | Why it will actually move |
|---|---|---|
| `GraphStore` | Use-cases from neo4aas + PostgreSQL | External library and a running database. Tests of analytics and constraint reporting should not need a database container. **Likely the highest-risk seam.** |
| `SchemaValidator` | Use-cases from XSD / JSON-Schema mechanics | Three metamodel versions (V3.0, V3.1, V3.2) today, more later; validator libraries are a technology choice. |
| `CorpusReader` | Use-cases from AASX / JSON / XML file handling | Three input formats; AASX is a ZIP package with its own quirks. Uploaded files are untrusted input. |
| `TemplateSource` | Conformance check from where submodel templates come from | IDTA templates and user-uploaded custom templates are two sources for the same thing. |
| `ReportRenderer` | Use-cases from output format | JSON and PDF today; the result model must not know about either. |

## Name ports for what the caller needs

Name a port for **what the caller needs**, not for the technology behind it. `GraphStore`, not `PostgresClient` or `Neo4aasWrapper`: if neo4aas changes its API or the constraint checker moves elsewhere, the name still holds and `app` does not change.

## Test: is this a real seam?

Ask: **"Can I write a fake for this that makes a test meaningfully cheaper?"**

- `GraphStore` → a fake turns "count submodels by semanticId over 100 files" from a PostgreSQL integration test into a millisecond unit test. Real seam.
- `CorpusReader` → a fake hands the analysis in-memory AAS objects; no fixture files needed for most tests. Real seam.
- A hypothetical `IdShortFormatter` port → a fake buys nothing. Not a seam; just call the function.

## When NOT to add a port

- One implementation, no test benefit, no plausible second implementation → call the code directly.
- The "abstraction" is a rename of the thing behind it (a `PostgresConnection` wrapper with psycopg's exact methods) → that is a wrapper, not a boundary.

Over-porting carries its own maintenance cost. Be sceptical of every port beyond the ones above.
