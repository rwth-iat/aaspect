# Budgets: what to actually do at each threshold

Budgets are a **smell detector**. Crossing one is not a violation to be silenced — it is a prompt to look at the file and ask what the second job is. Sometimes the honest answer is "nothing, this is a long but genuinely single-purpose mapping table" (for example, a table of semanticId prefixes to dictionaries). Say that and move on.

## File over 200 lines (soft)

Look for the second job. Usual suspects:

- **Parsing/classification mixed with orchestration** → extract the classification into `domain` as a pure function.
- **An analysis that also formats its output** → JSON/PDF rendering is a separate concern.
- **Several public helpers around one main function** → the helpers are probably a module of their own.

If you find no second job, leave it. Note *why* in a comment so the next person does not re-litigate it.

## File over 300 lines (hard)

Assume it has two jobs until proven otherwise. Split **before** adding anything new to it — appending to an over-budget file is how the "giant file nobody wants to open" actually gets created, one reasonable-looking commit at a time.

## Function over 40 lines

Almost always a sequence of named steps that were never given names. Extract each step into a function whose name says what it does. The extracted pieces are usually pure, and usually belong in `domain`.

## Public names over 5

A wide public surface makes a module hard to replace, because every consumer couples to a different part of it. Split by **consumer**: if `app` uses three names and `adapters` uses four others, those are two modules. (Counted from `__all__` if present, else top-level public functions and classes.)

## Modules per package over 8

The package has stopped being one concern. Group by sub-concern — for example `adapters/postgres/` splitting into `checks/`, `analytics/`, `submodels/`. Do this before it becomes a junk drawer where nothing can be found.

## Deliberate exceptions

If a budget is genuinely wrong for a file, do not fight it silently — say so in review or in an ADR.

If a budget is wrong *repeatedly*, it is the wrong budget: change it in `.claude/architecture.json`, which is the single place that defines it. Do not edit thresholds in a hook script.
