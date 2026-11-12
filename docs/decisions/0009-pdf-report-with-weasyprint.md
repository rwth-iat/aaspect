# 0009. Render the PDF report on the server with WeasyPrint

- **Status:** accepted (2026-11-12, after exporting a real corpus's report)
- **Date:** 2026-11-04
- **Relates to:** README "Features" (JSON/PDF download); ADR 0003, ADR 0005

## Context

Users download the report as JSON today; the README also promises a PDF. The PDF should
read like the report page in the browser, so it can be filed or sent to someone who has
no access to the running server.

Someone has to lay the page out on A4 sheets. Either the user's browser does it through
its print dialog, or the server produces a file. A browser print needs nothing new on the
server, but it is not a download, and the result differs between browsers.

AASpect will be hosted publicly. A server-side renderer runs on report text that comes
from uploaded files, and it costs CPU and memory per request. Measured with WeasyPrint 70
on synthetic reports (each page table capped at 200 rows, 20 locations per finding):
a small report takes 0.1–0.9 s; four sections with eight full tables and 60 rules each
give 399 pages in 28 s and 1.5 GB of memory. CSS grids that span pages lay out in
quadratic time: before the print stylesheet stacked them, four 200-row bar charts took
35 s, and a large report reached 12 GB before it was stopped.

On a real corpus (2026-11-12, the benchmark set per-vendor-100 of ADR 0008: 1,026 files,
517 MB, every analysis run) the export in the compose container took 35 s for 432 pages
and 1.4 MB.
The render process peaked at 1,110 MiB of address space and 963 MiB resident, about
half of the 2 GiB limit the export runs under.

## Decision

The server renders the report page to PDF with WeasyPrint. The PDF holds the report page
only (summary, charts, every section and its findings), not the per-file pages.

- `adapters/web` renders the page as one standalone HTML document: stylesheets inline,
  no scripts, no navigation, no links to other report pages (they would carry the
  report's key).
- `adapters/report_pdf` turns that HTML into PDF bytes behind the existing
  `ReportWriter` port. `main.py` hands it the renderer; the two adapters do not import
  each other.
- WeasyPrint fetches nothing: its URL fetcher refuses every URL, so uploaded text cannot
  make the server load a file or reach the network.
- `print.css` serves the export and the browser's print alike, and avoids layouts the
  renderer handles slowly or not at all (grids spanning pages, `<meter>`, page styles
  inside SVG). Dark colours and narrow-screen rules apply to screens only; `print.js`
  opens folded parts on every page while the browser prints.
- Downloads, JSON and PDF alike, are offered for finished reports only. Each is made once
  and kept with its report until the report expires, so asking again costs nothing. A
  failed export is kept the same way, as it would fail again at the same cost; only
  "busy" (`TryAgainLater`) is not. Kept files share a budget of 256 MB, the oldest
  dropped first.
- One export runs at a time by default; a second is refused, not queued. Its process gets
  its own memory limit and one deadline from start to finished file, and sends raw bytes
  of bounded size, never a pickle.

## Consequences

**Good:** The PDF is a real download next to the JSON one. It reuses the report templates,
so a new analysis appears in the PDF without changes (ADR 0003). WeasyPrint needs no
browser and runs no JavaScript, so the attack surface stays small. It is BSD-licensed.

**Bad:** Pango, fonts and WeasyPrint's Python packages grow the image from 254 MB to
375 MB. WeasyPrint is pure Python: a large
report holds the interpreter for tens of seconds and over a gigabyte of memory, so a
render must not run in the server process unguarded; it needs its own process with a
time and memory limit, and only a few at once. A finished report's first PDF still costs
that much; the cache only makes repeats free. Nothing is downloadable while an analysis
runs. The print layout is a second layout to
keep working: a new CSS grid or chart in the web page can be slow or wrong in the PDF,
and only rendering it shows that. Per-file details exist only in the browser and the JSON.

**Neutral:** The renderer supports most but not all of CSS; where they differ, the export
gets its own markup (bars as boxes instead of `<meter>`), chosen in the templates.

## Alternatives considered

| Option | Why not |
|---|---|
| Headless Chromium (Playwright) | Pixel-identical, but adds a browser of 300 MB+ to the image, and a browser on a public server is a larger attack surface to sandbox. |
| Print stylesheet only, the browser saves the PDF | No new dependency and no server load, but no file download, and the output differs between browsers. Kept as a side effect: the same `print.css` applies. |
| Report page plus every file page | Length and render time grow with the corpus; 100+ files give hundreds of pages. |
| ReportLab, building the PDF from the report types | A second renderer to keep in step with the templates; the PDF would drift from the page. |

## Revisit when

- A real large corpus report is exported and its render time or memory exceeds the limits
  set for the worker.
- Users need per-file details on paper.
