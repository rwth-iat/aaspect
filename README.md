# AASpect

**AASpect** is a tool for analyzing corpora of Asset Administration Shells (AAS).
It is built on [neo4aas](https://github.com/rwth-iat/neo4aas), which maps AAS data into a
Neo4j graph and checks it against the metamodel constraints.

> **Status:** early stage. The schema check works, with its web UI and JSON download
> (see [Running](#running)); everything marked *planned* below is not built yet.

## Features

Upload a set of AAS files (e.g. 100 AASX, JSON or XML files) in a web UI, start the
analysis, view the results in the browser and download them as **JSON** or **PDF**.
*Available: upload, report page, JSON download. Planned: PDF.*

### Compliance

- **Schema check** *(available)*: validate every file against the official AAS JSON and
  XML schemas (metamodel V3.0, V3.1, V3.2) and group recurring schema violations. The
  schemas are IDTA's (CC BY 4.0) and are not shipped: AASpect downloads them at startup
  from [admin-shell-io/aas-specs-metamodel](https://github.com/admin-shell-io/aas-specs-metamodel),
  pinned to one commit per version and checked by size and SHA-256.
- **Metamodel constraints** *(planned)*: import the corpus into Neo4j with neo4aas and
  evaluate the `AASd-xxx` constraints of the metamodel (IDTA-01001) with its constraint
  checker. Violations are reported per constraint and per file.

### Analytics *(planned)*

- **Submodels:** which submodels are used, and how often. Split into IDTA-standardized
  and proprietary submodels.
- **Semantic IDs:** which semantic IDs are used, which identification schemes
  (ECLASS IRDI, IEC CDD IRDI, IRI, URN, UUID, …) and which dictionaries they point to.
- **Submodel element types:** distribution of `Property`, `SubmodelElementCollection`,
  `SubmodelElementList`, `MultiLanguageProperty`, `File`, …
- **Value types:** which `valueType`s (`xs:string`, `xs:double`, …) are assigned.
- **Metamodel attributes:** how often optional attributes are populated (`description`,
  `displayName`, `category`, `semanticId`, `qualifiers`, …).

### Submodel template conformance *(planned)*

- Match each submodel to its IDTA submodel template by its semanticId.
- Report missing mandatory elements, cardinality violations, wrong element or value
  types and elements that the template does not define.
- Custom templates can be uploaded in addition to the IDTA templates.

### Deployment

- Runs with Docker (`docker compose up`): the aaspect web app and a Neo4j server with
  APOC and the DozerDB plugin, which gives every analysis a database of its own.

---

## Running

The schema check with its web UI works today:

```bash
uv sync
uv run aaspect          # then open http://127.0.0.1:8000
```

Upload AASX, JSON or XML files, or a whole folder, and choose a metamodel version or
"auto". The report page opens at once and updates itself as each step finishes. It shows the version of every file and groups recurring schema
violations; it can be downloaded as JSON. Reports are kept in memory only and are lost
when the server stops.

At startup the server downloads the official schemas (about 330 KB) and serves nothing
before they have arrived. While the download fails it logs why and tries again, with
pauses growing from 30 seconds to 15 minutes; a changed file or a missing path is logged
as an error, since it needs the operator.

### With Docker

```bash
echo "AASPECT_NEO4J_PASSWORD=$(openssl rand -hex 16)" > .env
docker compose up --build   # then open http://127.0.0.1:8000
```

The database password is read from `.env` (at least 8 characters); compose refuses to
start without it. The database publishes no port; only the web app reaches it. Its files
live in an unnamed volume that each `docker compose down` leaves behind; use
`docker compose down -v` to delete them as well.

The container runs as an unprivileged user on a read-only file system and is reachable
from this machine only. `compose.yaml` sets `AASPECT_VALIDATION_WORKERS` to 4 so that
all workers at their memory limit fit the container's 10 GB; other settings are passed
the same way, under `environment:`. The container needs outbound HTTPS for the schema
download, or `AASPECT_DOWNLOAD_URL` pointing at a mirror.

## Configuration

AASpect reads `AASPECT_*` environment variables once at startup, e.g.
`AASPECT_MAX_FILES=500 uv run aaspect`. Values must be positive whole numbers (except
host names, addresses and credentials); sizes are in bytes. An invalid value stops the server at startup.

All uploaded content is treated as hostile. The limits below keep one upload from
exhausting memory, CPU or the server's attention; the defaults leave wide margins over
real vendor corpora (largest file seen: 9 MB, slowest validation: 0.09 s, largest AASX
part: 1 MB).

### Server

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_HOST` | `127.0.0.1` | Interface to listen on. Loopback only by default: exposing the server is a deliberate choice. |
| `AASPECT_PORT` | `8000` | Port to listen on. |
| `AASPECT_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names the server answers to; other names are refused (protects against DNS rebinding). Add the public name when changing `AASPECT_HOST`. |

### Uploads and analyses

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_MAX_UPLOAD_BYTES` | `536870912` (512 MB) | Total size of one upload request. Checked while the data arrives. |
| `AASPECT_MAX_FILES` | `2000` | Files per upload. A chosen folder is cut to this many files in the browser. |
| `AASPECT_MAX_CONCURRENT_ANALYSES` | `2` | Analyses running at once. Further uploads get "busy, try again" before anything is read, so at most this many uploads are held in memory. |
| `AASPECT_MAX_STORED_REPORTS` | `20` | Reports kept in memory; the oldest is dropped first. |
| `AASPECT_MAX_DOCUMENT_BYTES` | `1073741824` (1 GB) | All documents of one analysis together, including parts unpacked from AASX packages. Documents beyond it are reported as not read. |
| `AASPECT_ANALYSIS_TIME_LIMIT_SECONDS` | `600` (10 min) | Time for one analysis, all steps together. Documents not validated or imported by then are reported as not checked or not imported. Importing about 900 MB of dense XML into the graph took about 5 minutes on its own, so this may need to be raised for uploads near the size limit. |

### AASX packages

An AASX is a ZIP archive. AASpect reads only its AAS parts, in memory, and never
unpacks anything to disk.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_MAX_PART_BYTES` | `104857600` (100 MB) | Unpacked size of one part. Enforced while reading, not taken from the ZIP header. |
| `AASPECT_MAX_ARCHIVE_ENTRIES` | `10000` | Files inside one package, including attachments that are never read. |
| `AASPECT_MAX_COMPRESSION_RATIO` | `200` | Unpacked size divided by packed size of one part. AAS data reaches about 60; ZIP bombs reach thousands. |
| `AASPECT_MAX_AAS_PARTS` | `100` | AAS parts named by one package. A part named twice is read once. |

### Downloads

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_DOWNLOAD_URL` | `https://raw.githubusercontent.com` | Where third-party files, such as the official schemas, are downloaded from: GitHub's raw file server, or a mirror serving the same paths (`<repository>/<commit>/<path>`). HTTPS only, no redirects, through the proxy in `HTTPS_PROXY` if set; each file is checked against its pinned size and SHA-256, so a mirror cannot change it. No user or password in the URL. |

### Schema validation

Each validation runs in a separate worker process, which is killed and replaced when it
exceeds its limits; the file then gets a "not validated" finding.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_VALIDATION_WORKERS` | `8` | Worker processes, i.e. documents validated in parallel. |
| `AASPECT_VALIDATION_TIMEOUT_SECONDS` | `30` | Time for one document and version. Some values (very long ones that fail a pattern) make libxml2 extremely slow. |
| `AASPECT_WORKER_MEMORY_BYTES` | `2147483648` (2 GB) | Memory of one worker process. |
| `AASPECT_MAX_VIOLATIONS_PER_DOCUMENT` | `1000` | Violations listed per document and version; a note says when there were more. |

### Graph database

The metamodel constraint check imports each corpus into a database of its own on a
Neo4j server with the DozerDB plugin (see `compose.yaml`), and drops it afterward.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_NEO4J_URI` | `bolt://127.0.0.1:7687` | Address of the Neo4j server. |
| `AASPECT_NEO4J_USER` | `neo4j` | User AASpect logs in as. It creates and drops databases, so it needs administration rights. |
| `AASPECT_NEO4J_PASSWORD` | none | Password of that user. Never shown in logs or error messages. Without it, the graph import is skipped. |

### Exposing the server

Before binding to another interface, set `AASPECT_ALLOWED_HOSTS` to the server's public
name and put a reverse proxy in front: AASpect does not time out uploads that arrive
very slowly, and it has no user accounts. A report's link is its only protection.

---

## Project Structure

Based on the [rwth-iat Python project template](https://github.com/rwth-iat/python-project-template).

The code is layered so that the analysis rules never depend on a library, file format or
server: `domain` depends on nothing, `ports` only on `domain`, and `app` and `adapters`
only on those two. `main.py` alone wires the adapters to the use-cases.

```text
src/aaspect/
├── domain/        Analysis rules and result types: report sections, findings, tables,
│                  version selection, grouping of violations. Pure Python, no I/O.
│                  metamodel.py holds everything that differs between metamodel
│                  versions: names, XML namespaces, pinned schemas.
├── ports/         Interfaces the use-cases depend on: read uploads, validate a
│                  document, write a report, parse and import into a graph,
│                  download a pinned file.
├── app/           Use-cases: analyze a corpus, run the schema check, import a corpus
│                  into a graph database.
├── adapters/      Implementations of the ports, one package per outside concern:
│   ├── files/         read JSON, XML and AASX uploads in memory, within limits
│   ├── download/      download pinned files over HTTPS
│   ├── schema/        validate with jsonschema-rs and lxml in isolated worker
│   │                  processes
│   ├── neo4aas/       convert documents, import them with neo4aas, one database
│   │                  per analysis on DozerDB
│   ├── report_json/   JSON report download
│   └── web/           FastAPI + Jinja2 UI, templates/ and static/
├── config/        Settings from AASPECT_* environment variables
└── main.py        Composition root: builds the adapters and starts the server
tests/             Mirrors src/aaspect/; tests/test_main.py drives the whole app over HTTP.
                   Pinned third-party files are downloaded once into .cache/
Dockerfile         Image with the installed package only, run as an unprivileged user
compose.yaml       Local deployment with resource limits
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

The import into Neo4j is tested against a real server only when one is given, e.g. a
DozerDB container with its port published:

```bash
AASPECT_TEST_NEO4J_URI=bolt://127.0.0.1:7687 AASPECT_TEST_NEO4J_PASSWORD=... \
  uv run python -m unittest tests.adapters.neo4aas.test_graph
```

CI runs these checks on every push to `main` and on pull requests.

## License

MIT, see [LICENSE](LICENSE).
