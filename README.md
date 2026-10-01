# aaspect

**aaspect** is a tool for analyzing corpora of Asset Administration Shells (AAS).
It is built on [neo4aas](https://github.com/rwth-iat/neo4aas), which maps AAS data into a
Neo4j graph and checks it against the metamodel constraints.

> **Status:** early stage. This repository contains the project structure only; the
> features below are planned.

## Planned features

Upload a set of AAS files (e.g. 100 AASX, JSON or XML files) in a web UI, start the
analysis, view the results in the browser and download them as **JSON** or **PDF**.

### Compliance

- **Schema check:** validate every file against the official AAS JSON and XML schemas
  (metamodel V3.0, V3.1, V3.2) and group recurring schema violations.
- **Metamodel constraints:** import the corpus into Neo4j with neo4aas and evaluate the
  `AASd-xxx` constraints of the metamodel (IDTA-01001) with its constraint checker.
  Violations are reported per constraint and per file.

### Analytics

- **Submodels:** which submodels are used, and how often. Split into IDTA-standardized
  and proprietary submodels.
- **Semantic IDs:** which semantic IDs are used, which identification schemes
  (ECLASS IRDI, IEC CDD IRDI, IRI, URN, UUID, …) and which dictionaries they point to.
- **Submodel element types:** distribution of `Property`, `SubmodelElementCollection`,
  `SubmodelElementList`, `MultiLanguageProperty`, `File`, …
- **Value types:** which `valueType`s (`xs:string`, `xs:double`, …) are assigned.
- **Metamodel attributes:** how often optional attributes are populated (`description`,
  `displayName`, `category`, `semanticId`, `qualifiers`, …).

### Submodel template conformance

- Match each submodel to its IDTA submodel template by its semanticId.
- Report missing mandatory elements, cardinality violations, wrong element or value
  types and elements that the template does not define.
- Custom templates can be uploaded in addition to the IDTA templates.

### Deployment

- Runs with Docker (`docker compose up`): the aaspect web app plus a Neo4j instance
  with APOC.

---

## Project Structure

Based on the [rwth-iat Python project template](https://github.com/rwth-iat/python-project-template).

```text
.
├── pyproject.toml
├── README.md
├── .gitignore
├── LICENSE
├── precommit.py
├── src/
│   └── aaspect/
│       ├── __init__.py
│       └── main.py
└── tests/
    └── test_main.py
```

---

## Development Setup

Install Python and dependencies using [uv](https://docs.astral.sh/uv/):

```bash
uv python install
uv sync --group dev
```

Run the same checks as CI (formatting, linting, type checking, tests with coverage,
package build):

```bash
uv run python precommit.py
```

CI runs these checks on every push to `main` and on pull requests.

## License

MIT, see [LICENSE](LICENSE).
