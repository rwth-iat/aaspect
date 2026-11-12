# Splitting a module without breaking it

The order matters. Each step leaves the tests green, so you can stop at any point.

## 1. Name the two jobs

Write the two sentences down before touching code:

> "This module (a) classifies semanticIds into identification schemes, and (b) queries PostgreSQL for all semanticIds in the corpus."

If you cannot write two clear sentences, you do not yet know how to split it. Keep reading the code.

## 2. Extract the pure core first

Pull the logic that needs no I/O into `src/aaspect/domain/` as a plain function. This is the highest-value step and the safest — pure functions have no wiring to break.

```
before:  class SemanticIdAnalysis: def run(self): ...  # SQL, classification, counting

after:   domain/semantic_ids.py   classify(semantic_id: str) -> Scheme      (pure)
         the original class calls it, and now only handles the I/O
```

Move its tests at the same time. They should get *faster* and lose their fakes.

## 3. Extract the port, if a seam appeared

If the leftover I/O part is something `app` should not know about, declare its `Protocol` in `src/aaspect/ports/` and have the use-case depend on that instead.

Check `references/seams.md` first — do not add a port that buys nothing.

## 4. Move the implementation into an adapter

The remaining I/O code becomes `src/aaspect/adapters/<concern>/`. It should now be thin: if there is still logic in it worth testing without I/O, that logic escaped from `domain` — send it back.

## 5. Rewire once

Update `src/aaspect/main.py`. It is the only module that should need changing.

**If step 5 requires edits in more than one place, the split is not finished** — something is still constructing its own dependencies.

## 6. Re-check

`python .claude/hooks/brick_check.py --all` and `uv run python precommit.py`. Both new modules should be under budget and the layering clean.

## Anti-patterns

- **Splitting by size, not by job.** Cutting a 400-line file at line 200 produces two files that must be read together — strictly worse than one. Split along the seam or not at all.
- **A `utils.py` / `helpers.py` / `common.py` landing zone.** These have no single reason to change, so they grow forever and couple everything to everything. Name modules for what they *do*.
- **Splitting for its own sake into a module only one caller will ever use.** One brick doing two tiny related things beats two modules with a hop between them.
