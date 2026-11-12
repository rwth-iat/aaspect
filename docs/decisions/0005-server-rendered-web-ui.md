# 0005. Server-rendered web UI with FastAPI and Jinja2

- **Status:** accepted
- **Date:** 2026-10-07
- **Relates to:** README "Planned features" (web UI, JSON/PDF download); ADR 0001, ADR 0003

## Context

The UI has four jobs: upload files and choose a metamodel version (or auto), wait for
the analysis, show the report, and download it. It is "form in, document out". Nothing
is edited in the browser and nothing changes live while the user clicks around.

All report text can come from uploaded files (idShorts, descriptions, ids, messages that
quote them). Text that reaches the page unescaped lets a crafted file run script in the
user's browser (XSS). The schema check finishes in seconds. The graph-based checks (on
Neo4j then, on PostgreSQL since ADR 0008) take minutes, so the UI must be able to show
progress.

Interactive exploration (filtering thousands of findings in the browser, linked charts,
drilling into a file's element tree) may be wanted later, but it is not needed now.

## Decision

The web UI is rendered on the server: FastAPI for routing and uploads, Jinja2 templates
for HTML, served by uvicorn. It lives in `adapters/web`.

- Autoescape is on for every template. Report content is never marked safe (`|safe`,
  `Markup`). Templates that need raw HTML build it from trusted constants only.
- Pages send a Content-Security-Policy that allows scripts from the app's own origin
  only. Any JavaScript lives in static files. There are no inline scripts and no CDN.
- One generic report template renders any `Report` (ADR 0003). Adding an analysis does
  not touch templates.
- Long-running jobs, when they come, use polling: a small static script, or htmx served
  from the app itself. No SPA.

## Consequences

**Good:** One language and one toolchain. No npm and no build step. Escaping is on by
default, so every value is safe unless someone deliberately opts out. FastAPI streams
large uploads to temporary files and can run work outside the request. The JSON
download is already the API that a later SPA would consume, so this choice does not
block interactive exploration.

**Bad:** Every interaction is a full page load. Large reports (thousands of findings)
cannot be filtered in the browser, so filtering and paging have to happen on the server
through query parameters. Pyright does not check templates, so a wrong field name
fails only when the page renders. Every template therefore needs a render test.
Validation is CPU-heavy: called directly from an `async` route, it blocks the server, so
it has to run in a worker thread or process. Upload parsing relies on `python-multipart`,
which has had denial-of-service advisories. Keep it current and enforce the upload
limits before parsing.

**Neutral:** Any interactive features added later will most likely arrive as a separate
frontend that reads the JSON report. That frontend would be its own adapter, next to
this one, not a rewrite of it.

## Alternatives considered

| Option | Why not |
|---|---|
| FastAPI JSON API + SPA (React/Vue) | Adds npm, a build step and a second test suite, and the UI has no rich state that would need them. Can be added later on top of the JSON report. |
| Flask + Jinja2 | Same model. Less built-in support for typed input, streamed uploads and background work. |
| Static HTML report file, no server | No upload flow, and no way to run the Neo4j-based analyses on demand. |

## Revisit when

- Users regularly need to filter or explore reports that are too large to read as one
  page.
- Polling proves too coarse for progress reporting. *2026-11-12:* the graph analyses have
  arrived; the report page polls `/reports/{key}/status` and that suffices so far.
