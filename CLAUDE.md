# AASpect — working rules

Tool for analysing corpora of Asset Administration Shells (AASX/JSON/XML): schema validation, metamodel constraint checks as SQL on PostgreSQL (one schema per analysis, graph mapped by [neo4aas](https://github.com/rwth-iat/neo4aas)), analytics, submodel template conformance, results as JSON/PDF in a web UI.

Planned scope is authoritative in `README.md` — cite it, do not restate it. Most of it is not built yet.
Past decisions: `docs/decisions/` (created with the first ADR).

## Hard rules

These outrank every other consideration, including "it's just a quick test". The `brick-check` hook blocks on the first two.

1. **SQL is never built by string formatting.** Values from uploaded AAS files go in as query parameters; SQL identifiers (schema names) are composed with `psycopg.sql.Identifier` inside `sql.SQL(...).format(...)`. Neither an f-string, `+`, `%` nor `.format` touches the query text or the text of an `sql.SQL`.
2. **No database credentials in code** (no password literal, no connection URL with a password). They come from config/environment.
3. **Uploaded files are untrusted input** — every value inside them too (idShorts, descriptions, semanticIds, files embedded in AASX packages, custom templates).

## Layers — imports point inward only

```
domain ← ports ← app ← adapters ← main.py
```

All under `src/aaspect/`.

| Layer | Holds | May import |
|---|---|---|
| `domain` | Pure analysis rules: element model as the analysis sees it, semanticId classification, statistics, finding/violation types. No I/O, no third-party packages. | `domain` |
| `ports` | `Protocol`s only. Zero implementations. | `domain` |
| `app` | Use-cases: analyse a corpus, assemble a report. Orchestrates domain through ports. | `domain`, `ports` |
| `adapters/*` | Outside world, one sub-package per concern (e.g. neo4aas parsing, PostgreSQL, schema validation, file reading, templates, report output, web). | `domain`, `ports` |
| `config` | Settings (PostgreSQL connection, upload limits, ...), read once at startup. | `domain` |
| `main.py` | Composition root — the **only** module that constructs adapters. | anything |

`app` importing an adapter is always a mistake: what you want is a new method on a port.
An adapter importing a sibling adapter is always a mistake: hoist the shared thing into `domain`, or wire both in `main.py`.

## Build in bricks

- **One reason to change per module.** If a module would change for two unrelated causes, it is two modules.
- **Name the seam before you write code.** Say out loud which layer this belongs in. If that's unclear, the design is unclear — resolve it first.
- **Port before implementation.** Write the protocol, then a use-case against it, then the adapter. The most-likely-to-change piece is written last and stays smallest.
- **Wire in exactly one place** — `src/aaspect/main.py`. No singletons, no module-level construction, no service locator.
- **Test at the cheapest layer** that proves the thing. Domain logic needs no database.

| Budget | Soft | Hard |
|---|---|---|
| File | 200 LOC | 300 LOC |
| Function | 40 LOC | — |
| Public names per module | 5 | — |
| Modules per package | 8 | — |

Budgets detect design smells, not style violations. Crossing one means "this probably has two jobs" — go look. The hook will tell you; it does not block.

## Working efficiently

- Session start injects a repo map with per-file LOC and the decision index. **Read that before globbing** — it usually already answers "where does this live?".
- Grep for symbols, not files. Read the specific function, not the whole module.
- Prefer `Edit` over rewriting a file. Never re-read a file just to confirm an edit landed.
- Touch one module per change. A change spanning four layers is a design problem wearing a task costume.
- **If understanding a change needs more than three files open at once, the seam is in the wrong place.** Say so instead of pushing through — that signal is the entire reason this structure exists.

## How to ask a question

The person you are asking knows the tools but not necessarily every protocol and standard underneath them. A question they cannot evaluate is not a decision being made — it is one being waved through.

- **One decision at a time.** Ask it, wait for the answer, then open the next. Several at once produced "I have no clue where we are at now" and cost several turns to recover.
- **Problem first.** State the real-world situation, then what goes wrong if it is chosen badly, and only then the options. Never a protocol or library name as the opening move.
- **Say where things stand** in two or three lines before asking, so the question has a place to sit.
- **Always offer "not sure — talk me through it".** It gets used, and it works.
- **Affirm what is sound before correcting what is not.** The instincts here have been good; corrections have almost always been about a factual detail that could not have been known.

This applies to the ADRs too — an ADR whose Context only makes sense to someone who already knows the answer has failed.

## Before you decide

Non-trivial technical choices get checked against `docs/decisions/` **first**. If new work contradicts an existing ADR, surface the conflict rather than silently diverging — see the `decision-record` skill.

Decisions marked `provisional` rest on assumptions not yet verified (neo4aas/PostgreSQL behaviour, real corpus size and shape). When you learn the real answer, revisit the ADR; do not quietly build on the guess.

## Tooling

| | |
|---|---|
| Skills | `modular-design` · `decision-record` |
| Agents | `code-review-logic-architecture` · `code-review-security` |
| Commands | `/brick-check` (audit structure) · `/adr <topic>` · `/reassess` (decisions vs. reality) |
| Hooks | after Write/Edit: ruff format + fix, brick-check · session start: repo map · stop: pyright · git commit-msg: message rules (install: `ln -s ../../.claude/hooks/commit_msg.py .git/hooks/commit-msg`) |
| Rules config | `.claude/architecture.json` — change limits **there**, nowhere else |
| Check locally | `uv run python precommit.py` (CI suite) · `python .claude/hooks/brick_check.py --all` |

Hooks run with plain `python` (stdlib only, ≥ 3.10) and use ruff/pyright from `.venv`; without `uv sync --group dev` the format and typecheck hooks silently do nothing.

Language: code, comments, ADRs and commit messages in **English**.

## Code comments

- Default to no comment. Well-named functions and variables should explain *what* the code does.
- Only comment to explain *why*: non-obvious decisions, workarounds, edge cases, links to issues/specs, or surprising behavior.
- Never write comments that restate the code, narrate your changes, or address the reader
  (e.g. "# Added error handling", "# Now we loop over users", "# Updated to use new API").
- Don't leave comments about what was removed or changed. That belongs in the commit, not the code.
- Keep docstrings for public APIs short: one line summary, then params/returns only if non-obvious.

Bad:  `# Increment the counter by one`
Good: `# Retry once: PostgreSQL refuses connections until its container is healthy`

## Commit messages

- Follow Conventional Commits: `type(scope): summary` (types: feat, fix, refactor, docs, test, chore, perf).
- Summary line: imperative mood, max ~50 chars, no trailing period ("fix(auth): handle expired refresh tokens").
- Leave a blank line, then a body wrapped at 72 chars explaining *why* the change was made
  and any notable trade-offs. Skip the body for trivial changes.
- Describe the change's intent, not a file-by-file list of what was edited.
- Make one logical change per commit; if the work spans unrelated concerns, propose splitting it.
- Compact the message to the minimum
- Reference issues when relevant (`Closes #123`).
- No emojis, no "This commit...", no marketing language.
- Don't add Co-authored by ...
