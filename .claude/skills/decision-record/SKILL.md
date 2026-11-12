---
name: decision-record
description: Use before making or changing any non-trivial technical decision - choosing a library (schema validator, PDF renderer, web framework), a graph model or query approach, a result format, an error shape, a deployment assumption - and whenever new work might contradict how the project already does something. Checks docs/decisions/ first, surfaces conflicts instead of silently diverging, and records load-bearing choices as ADRs. Triggers on "should we use", "let us switch to", "why is it done this way", a change of approach, or a provisional assumption getting verified.
---

# Decisions get checked before they get made

The failure mode this prevents: a choice was made deliberately six months ago for a reason nobody remembers, and today it gets quietly reversed by someone who never saw the reasoning. The project then has two half-applied designs.

## Before deciding: read what already exists

```bash
ls docs/decisions/
grep -ril "<topic>" docs/decisions/
```

Then one of three cases applies.

### 1. An ADR already covers this, and you agree

Follow it. Do not re-derive it, do not re-explain it in the chat. Cite it: "per ADR 0004, constraint checks run through neo4aas."

### 2. An ADR covers this, and the new work contradicts it

**Stop and surface it to the user.** Do not silently diverge, and do not silently comply either — the ADR may well be wrong now. Say:

> ADR 0004 decided X because Y. What you are asking implies not-X. Has Y changed, or should this be an exception?

Then act on the answer: supersede the ADR (write the new one, mark the old `Superseded by NNNN`) or record the exception in the code with a comment pointing at the ADR.

The one thing never to do is leave the codebase and the record disagreeing.

### 3. Nothing covers it

If the choice is **load-bearing**, write an ADR. If it is not, just make it.

Load-bearing means at least one of:

- Reversing it later would touch more than one module.
- It rests on an assumption that could turn out false (how neo4aas behaves, what PostgreSQL supports, how IDTA templates are structured, how big real corpora get).
- A reasonable engineer would ask "why is it like this?" and the answer is not obvious from the code.

Naming a variable is not load-bearing. Choosing to compute analytics in SQL instead of in Python is.

## Writing one

Copy `references/template.md` to `docs/decisions/NNNN-kebab-title.md`, next number in sequence. Keep it under a page — an ADR nobody reads has failed at its only job.

The **Consequences** section is the part with real value. Include what this makes *harder*, not only what it makes possible. An ADR that lists only upsides was not a decision, it was an advertisement.

## Provisional decisions

Some decisions rest on an assumption that has not been checked against reality yet — typically behaviour of an external dependency (neo4aas, PostgreSQL, a schema library) or the shape of real-world AAS files. Any ADR resting on such an assumption:

- gets `Status: provisional — pending verification`
- names in **Revisit when** the exact observation that would settle it

When the real answer arrives, revisit the ADR **before** building further on it. Session start flags every provisional decision precisely so this does not get forgotten.

Building on a guess is fine. Forgetting that it was a guess is not.

## `/reassess`

Walks every ADR and compares it against what the code now does: violated, stale, provisional-but-now-answerable, or superseded in practice but not on paper. Run it when picking the project back up after a break, or before a release.
