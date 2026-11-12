# NNNN. <Short imperative title>

- **Status:** proposed | accepted | provisional — pending verification | superseded by NNNN
- **Date:** YYYY-MM-DD
- **Relates to:** README feature, ADR NNNN

## Context

What forced a decision here? State the constraint, not the solution. If this rests on an assumption rather than a verified fact, say so explicitly and say where the assumption came from.

## Decision

What we are doing, in one or two sentences. Present tense, active: "Constraint checks run as SQL against a per-analysis PostgreSQL schema."

## Consequences

**Good:** what this buys.

**Bad:** what this costs, what it makes harder, what we are giving up. *This section is the reason the ADR is worth writing.* A decision with no downsides listed was not analysed.

**Neutral:** what changes without being better or worse.

## Alternatives considered

| Option | Why not |
|---|---|
| ... | ... |

One line each. Enough that the next person does not repeat the evaluation, not a full essay.

## Revisit when

*(Required for `provisional`, good practice otherwise.)*

The specific, observable trigger that should reopen this — "when a 1000-file corpus is imported into PostgreSQL and timed", "when neo4aas releases a version with a different graph model", "when a second metamodel version needs a different XSD loader". Not "when we have time".
