# AASpect

**AASpect** is a tool for analyzing corpora of Asset Administration Shells (AAS).
It uses [neo4aas](https://github.com/rwth-iat/neo4aas) to map AAS data into a graph, which
it keeps in PostgreSQL and checks against the metamodel constraints.

> **Status:** early stage. All four analyses work: schema check, metamodel constraints,
> analytics and submodel template conformance, with a web report (a summary of the files
> with errors first, charts and a page per uploaded file) and JSON and PDF downloads (see
> [Running](#running)).

## Features

Upload a set of AAS files (e.g. 100 AASX, JSON or XML files) in a web UI, start the
analysis, view the results in the browser and download them as **JSON** or **PDF**.
*Available: upload, report page, JSON and PDF download. The PDF holds the report page,
not the pages per file.*

### Compliance

- **Schema check** *(available)*: validate every file against the official AAS JSON and
  XML schemas (metamodel V3.0, V3.1, V3.2) and group recurring schema violations. The
  schemas are IDTA's (CC BY 4.0) and are not shipped: AASpect downloads them at startup
  from [admin-shell-io/aas-specs-metamodel](https://github.com/admin-shell-io/aas-specs-metamodel),
  pinned to one commit per version and checked by size and SHA-256.
- **Metamodel constraints** *(available)*: import the corpus as a graph and evaluate the
  `AASd-xxx` constraints of the metamodel (IDTA-01001), ported from neo4aas's constraint
  checker to SQL. The whole corpus is checked by one version: the one chosen, else the most
  common one; files of other versions are named. Violations are grouped per constraint
  and located by file, object id and element path; an object shared by many files is
  listed once, with its first file and the number of files.

### Analytics *(available)*

Computed in the graph right after the import, before the constraint check. Every count
is over distinct contents: an object repeated identically in many files counts once.

- **Corpus size and structure:** shells, submodels, SubmodelElements and
  ConceptDescriptions; nesting depth of SubmodelElements and submodel references per
  shell (count, min, max, mean, median, standard deviation).
- **Submodels:** which submodels are used, and how often, grouped by semanticId and named
  by their most frequent idShort. Split by origin: the IDTA template their semanticId
  names (current, superseded or deprecated edition, see template conformance), else the
  dictionary of the identifier (IDTA `admin-shell.io`, ECLASS, IEC CDD or proprietary).
- **Semantic IDs:** semanticIds and supplementalSemanticIds of SubmodelElements, their
  identification schemes (IRDI, IRI, URN, UUID, other) and the dictionaries they point
  to (ECLASS, IEC CDD, IDTA, other).
- **Submodel element types:** distribution of `Property`, `SubmodelElementCollection`,
  `SubmodelElementList`, `MultiLanguageProperty`, `File`, …
- **Value types:** which `valueType`s (`xs:string`, `xs:double`, …) Properties and Ranges
  carry.
- **Metamodel attributes:** how often the optional attributes each kind of object can
  have are filled (`description`, `displayName`, `category`, `semanticId`, `qualifiers`,
  `extensions`, `embeddedDataSpecifications`, `administration`, …).
- **Languages:** MultiLanguageProperty against Properties of `xs:string`, and the
  language tags of MultiLanguageProperty values, descriptions and displayNames.
- **Assets:** `assetKind`, identification schemes of `globalAssetId`s and the names of
  `specificAssetIds`.

Rankings list the 100 most frequent values and sum up the rest. Values are compared on
their first 256 characters.

### Submodel template conformance *(available)*

- Match each submodel to its IDTA submodel template by its semanticId, ignoring the
  version of an IRDI. A current edition is preferred over a superseded one, and a
  superseded one over a deprecated one; the report names which was used.
- Report missing mandatory elements, cardinality violations, wrong element or value
  types (errors), and elements the template does not define, other idShorts and other
  semanticId versions (notes). Elements are matched by semanticId, ignoring IRDI
  versions also inside composite ids, else by idShort; numbered idShorts such as
  `Document{00}` match `Document01`. Where a template offers alternatives (list item
  kinds, interface variants sharing a semanticId), each element is compared with the
  one it fits; wildcard elements (`arbitrary`) stand for any further elements of their
  type. Collections, lists and entities are compared level by level. Submodels with more
  than 100,000 elements are named, not checked.
- The templates are downloaded at runtime from one pinned commit of IDTA's
  [submodel-templates](https://github.com/admin-shell-io/submodel-templates) repository
  (CC BY 4.0) and checked against the hashes in
  `src/aaspect/adapters/templates/manifest.json`; AASpect ships none of them.
  `tools/template_manifest.py <commit>` moves to newer templates.
- Own templates can be uploaded with an analysis, as AAS files (AASX, JSON or XML), when a
  graph database is configured. Where an uploaded and an IDTA template match a submodel
  equally (both exactly, or both only without the IRDI version), the uploaded one is
  used; they count for that analysis only and are named "uploaded" in the report.
  Unreadable or oversized ones are listed. While the IDTA templates are not available,
  the uploaded ones are used alone, with a warning. A submodel whose comparison would
  take too long is named, not checked.

### Deployment

- Runs with Docker (`docker compose up`): the aaspect web app and a PostgreSQL server,
  which gives every analysis a schema of its own.

---

## Running

Start the server:

```bash
uv sync
uv run aaspect          # then open http://127.0.0.1:8000
```

Started like this, without a graph database, the server runs the schema check only; the
graph import, constraint check, analytics and template conformance show as "not
configured". [With Docker](#with-docker) starts the database as well, and
[Graph database](#graph-database) connects to one of your own.

Upload AASX, JSON or XML files, or a whole folder, and choose a metamodel version or
let it be detected per JSON file ("auto"), trying the oldest or the newest version
first. XML files always use the version of their namespace. The report page opens at
once and updates itself as each step finishes. It starts with a summary of the files
with errors, groups recurring findings by rule and gives every uploaded file a page of
its own. Once the analysis has finished, it can be downloaded as JSON or PDF. Reports are
kept in memory only and are lost when the server stops.

At startup the server downloads the official schemas (about 330 KB) and serves nothing
before they have arrived. While the download fails it logs why and tries again, with
pauses growing from 30 seconds to 15 minutes; a changed file or a missing path is logged
as an error, since it needs the operator.

### With Docker

```bash
echo "AASPECT_POSTGRES_PASSWORD=$(openssl rand -hex 16)" > .env
docker compose up --build   # then open http://127.0.0.1:8000
```

The database password is read from `.env`; compose refuses to start without it. The
database publishes no port; only the web app reaches it. Its files live in the volume
`postgres-data`, which `docker compose down` keeps. The server sets its password only on
the first start, so after changing it in `.env`, run `docker compose down -v` to delete
the volume as well. The database runs as an unprivileged user on a read-only file
system, with 8 GB of memory, of which 2 GB are shared buffers; with PostgreSQL's
defaults the analytics are several times slower. On its first start,
`deploy/postgres/app-role.sh` creates the role `aaspect` that the web app logs in as. It
may create schemas in the database `aaspect` and nothing more, and each of its server
processes may hold at most 5 GB of temporary files at a time. The superuser keeps no
password; for maintenance, use `docker compose exec postgres psql`.

Earlier versions kept the graph in a DozerDB container. When upgrading such a setup,
replace `AASPECT_NEO4J_PASSWORD` in `.env` with `AASPECT_POSTGRES_PASSWORD`, and start
with `docker compose up --build --remove-orphans`, so that the old `dozerdb` container is
removed.

The container runs as an unprivileged user on a read-only file system and is reachable
from this machine only. `compose.yaml` sets `AASPECT_VALIDATION_WORKERS` to 4 so that
all workers and a PDF export at their memory limits fit the container's 13 GB; other
settings are passed the same way, under `environment:`. The container needs outbound
HTTPS for the schemas (about 330 KB, at startup) and the IDTA submodel templates (about
36 MB, in the background), or `AASPECT_DOWNLOAD_URL` pointing at a mirror.

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
| `AASPECT_UPLOAD_TIME_LIMIT_SECONDS` | `300` (5 min) | Time for one upload to arrive completely; a slower one is refused. It holds an analysis slot while it arrives, so without a limit a few stalled connections would keep everyone else out. 512 MB in 5 minutes needs about 14 Mbit/s. |
| `AASPECT_MAX_STORED_REPORTS` | `20` | Reports kept in memory; the oldest is dropped first. |
| `AASPECT_MAX_DOCUMENT_BYTES` | `1073741824` (1 GB) | All documents of one analysis to analyze together, including parts unpacked from AASX packages. Documents beyond it are reported as not read. |
| `AASPECT_ANALYSIS_TIME_LIMIT_SECONDS` | `600` (10 min) | Time for one analysis, all steps together. Documents not validated or imported by then are reported as not checked or not imported, and constraints not checked or analytics not computed by then are listed as such; a database query still running 5 seconds later is cancelled. Importing about 900 MB of dense XML into the graph took about 5 minutes on its own, so this may need to be raised for uploads near the size limit. |
| `AASPECT_MAX_TEMPLATE_FILES` | `50` | Submodel template files uploaded with one analysis. |
| `AASPECT_MAX_TEMPLATE_BYTES` | `52428800` (50 MB) | Those template files together, and again the documents unpacked from them. They are read like the corpus, with the same package limits; a template with more than 5,000 elements, 1,000 siblings on one level, 16 list item kinds or an idShort longer than 128 characters is left out. |

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
| `AASPECT_DOWNLOAD_URL` | `https://raw.githubusercontent.com` | Where third-party files, the official schemas at startup and the IDTA submodel templates in the background, are downloaded from: GitHub's raw file server, or a mirror serving the same paths (`<repository>/<commit>/<path>`). HTTPS only, no redirects, through the proxy in `HTTPS_PROXY` if set; each file is checked against its pinned size and SHA-256, so a mirror cannot change it. No user or password in the URL. A failed template download is tried again every five minutes; until it succeeds, template conformance reports that the templates are not available. |

### Schema validation

Each validation runs in a separate worker process, which is killed and replaced when it
exceeds its limits; the file then gets a "not validated" finding.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_VALIDATION_WORKERS` | `8` | Worker processes, i.e. documents validated in parallel. |
| `AASPECT_VALIDATION_TIMEOUT_SECONDS` | `30` | Time for one document and version. Some values (very long ones that fail a pattern) make libxml2 extremely slow. |
| `AASPECT_WORKER_MEMORY_BYTES` | `2147483648` (2 GB) | Memory of one worker process. |
| `AASPECT_MAX_VIOLATIONS_PER_DOCUMENT` | `1000` | Violations listed per document and version; a note says when there were more. |

### PDF export

The PDF holds the report page, laid out by WeasyPrint. Each export runs in a process of
its own, killed when it exceeds its time or memory; a large report takes about half a
minute and 1.5 GB. Both downloads are offered once the analysis has finished; each is
made once and kept with the report until it expires, a failed export too. Kept files
share 256 MB; beyond that the oldest is dropped and made again when next asked for.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_PDF_EXPORTS` | `1` | Exports at the same time; further requests are refused until one finishes. `0` turns the PDF download off. |
| `AASPECT_PDF_MEMORY_BYTES` | `2147483648` (2 GB) | Memory of one export's process. |
| `AASPECT_PDF_TIMEOUT_SECONDS` | `60` | CPU time for one export; a report that needs more gets an error page pointing to the JSON download. An export still running 15 s after this time, for example on a busy server, is stopped and may be asked for again. |

### Graph database

The constraint check, analytics and template conformance work on a graph of the corpus:
each analysis imports it into a schema of its own on a PostgreSQL server (see
`compose.yaml`), and drops it afterward. Schemas left behind by a crash are dropped at
startup.

| Variable | Default | Meaning |
|---|---|---|
| `AASPECT_POSTGRES_HOST` | `127.0.0.1` | Address of the PostgreSQL server. |
| `AASPECT_POSTGRES_PORT` | `5432` | Its port. |
| `AASPECT_POSTGRES_DATABASE` | `aaspect` | Database the analyses keep their schemas in. |
| `AASPECT_POSTGRES_USER` | `aaspect` | User AASpect logs in as. It creates and drops one schema per analysis, so it needs the `CREATE` right on that database. |
| `AASPECT_POSTGRES_PASSWORD` | none | Password of that user. Never shown in logs or error messages. Without it, the graph import and every step after it show as "not configured". |
| `AASPECT_POSTGRES_SSLMODE` | `prefer` | libpq's `sslmode`. `prefer` encrypts if the server offers it but checks no certificate; for a server reached over a network, use `verify-full`, with the CA in `PGSSLROOTCERT`. |

### Exposing the server

Before binding to another interface, set `AASPECT_ALLOWED_HOSTS` to the server's public
name and put a reverse proxy in front that serves HTTPS, buffers each upload before
passing it on, and limits requests per client. AASpect has no user accounts: a report's
link is its only protection, so it must never travel over plain HTTP. Without buffering,
a few slow uploads still keep everyone else out for up to
`AASPECT_UPLOAD_TIME_LIMIT_SECONDS`; without a per-client limit, one client can keep every
analysis slot busy.

---

## Project Structure

Based on the [rwth-iat Python project template](https://github.com/rwth-iat/python-project-template).

The code is layered so that the analysis rules never depend on a library, file format or
server: `domain` depends on nothing, `ports` only on `domain`, and `app` and `adapters`
only on those two. `main.py` alone wires the adapters to the use-cases.

```text
src/aaspect/
├── domain/        Analysis rules and result types: report sections, findings, tables,
│                  version selection, grouping of violations, identifier classification
│                  and analytics tables, template matching and conformance rules, the
│                  report summary and its narrowing to one file. Pure Python, no I/O. metamodel.py holds everything that differs between
│                  metamodel versions: names, XML namespaces, pinned schemas, the
│                  constraint checker's rule set, and what each constraint means.
├── ports/         Interfaces the use-cases depend on: read uploads, validate a
│                  document, write a report, parse and import into a graph, count
│                  in it, download a pinned file.
├── app/           Use-cases: analyze a corpus, run the schema check, import a corpus
│                  into a graph database, check its constraints and templates,
│                  describe it.
├── adapters/      Implementations of the ports, one package per outside concern:
│   ├── files/         read JSON, XML and AASX uploads in memory, within limits
│   ├── download/      download pinned files over HTTPS
│   ├── schema/        validate with jsonschema-rs and lxml in isolated worker
│   │                  processes
│   ├── neo4aas/       convert documents for the import with neo4aas
│   ├── postgres/      one schema per analysis: import the graph, link references;
│   │                  checks/ holds the constraint rules, analytics/ the counting
│   │                  queries, submodels/ reads element trees for template conformance
│   ├── templates/     download the IDTA submodel templates listed in manifest.json
│   ├── report_json/   JSON report download
│   ├── report_pdf/    PDF report download, laid out by WeasyPrint in its own process
│   └── web/           FastAPI + Jinja2 UI, templates/ and static/
├── config/        Settings from AASPECT_* environment variables
└── main.py        Composition root: builds the adapters and starts the server
tests/             Mirrors src/aaspect/; tests/test_main.py drives the whole app over HTTP.
                   Pinned third-party files are downloaded once into .cache/
Dockerfile         Image with the installed package only, run as an unprivileged user
compose.yaml       Local deployment with resource limits
tools/             Development tools, e.g. writing the template manifest
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

The PostgreSQL store, its constraint checks and queries are tested the same way, against
any server the given user may create schemas on (port and user default to `5432` and
`postgres`):

```bash
AASPECT_TEST_POSTGRES_HOST=127.0.0.1 AASPECT_TEST_POSTGRES_PASSWORD=... \
  uv run python -m unittest discover -s tests/adapters/postgres -t .
```

CI runs these checks on every push to `main` and on pull requests.

## License

MIT, see [LICENSE](LICENSE).
