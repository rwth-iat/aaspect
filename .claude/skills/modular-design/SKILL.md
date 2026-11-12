---
name: modular-design
description: Use when adding a capability, creating a new module or package, deciding where code belongs, or when a file has grown past its budget. Enforces the domain/ports/app/adapters layering so later changes swap one brick instead of reworking the project. Triggers on "where should this go", "add a feature", "add an analysis", "this file is getting big", "refactor", "split this up", or any brick-check layering or size warning.
---

# Building in bricks

The goal is that a change six months from now touches **one small module plus one line of wiring** — not a 900-line module nobody wants to open. Everything below serves that.

## Before writing any code, answer three questions

1. **Which layer?** Say it explicitly: `domain`, `ports`, `app`, `adapters/<name>`, or `config` (all under `src/aaspect/`).
   Cannot answer cleanly? The design is unclear — resolve that first, do not start typing.
2. **What is the seam?** What interface separates the part that is *stable analysis logic* from the part that is *a technology choice we might reverse*? See `references/seams.md`.
3. **What changes it?** If you can name two unrelated causes, it is two modules.

## The order of work (this is the whole method)

```
1. domain/    pure function or dataclass         <- write FIRST, test with no fakes
2. ports/     the Protocol app needs
3. app/       the use-case, deps as parameters
4. adapters/  the implementation of the port     <- write LAST, keep smallest
5. main.py    one line of wiring
6. tests/     at the cheapest layer that proves it
```

The most-likely-to-change code is written last and is the thinnest. When neo4aas, psycopg, or a schema library shifts, you rewrite step 4 and nothing else.

## Rules that are not negotiable

- `app` **never** imports `adapters`. If you want to, what you actually want is a new method on a port.
- An adapter **never** imports a sibling adapter. Hoist into `domain`, or wire both in `main.py`.
- `domain` and `ports` import no third-party package and no I/O stdlib module (`os`, `pathlib`, `logging`, `zipfile`, ... — list in `.claude/architecture.json`). No clock, no logger.
- Dependencies arrive as parameters. No module-level construction, no singletons, no service locator.
- Wiring happens in `src/aaspect/main.py` only.

## Budgets

| Unit | Soft | Hard |
|---|---|---|
| File | 200 LOC | 300 LOC |
| Function | 40 LOC | — |
| Public names per module | 5 | — |
| Modules per package | 8 | — |

These detect **design smells**, not style violations. Over budget means "this probably has two jobs" — go look. See `references/budgets.md` for what to do at each threshold, and `references/splitting.md` for the safe split recipe.

## The strongest signal you have

**If understanding a change needs more than three files open at once, the seam is in the wrong place.**

Say so out loud rather than pushing through. That sentence is the reason this structure exists — a project degrades when that feeling gets ignored one commit at a time.

## Check your work

`/brick-check` (or `python .claude/hooks/brick_check.py --all`) audits the whole repo against `.claude/architecture.json`. Change limits there, never in a hook script.
