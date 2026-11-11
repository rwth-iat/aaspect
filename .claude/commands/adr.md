---
description: Record an architecture decision, or update an existing one
argument-hint: <topic, e.g. "where analytics aggregates run: SQL or Python">
---

Record an architecture decision about: **$ARGUMENTS**

Follow the `decision-record` skill. In short:

1. **Check first.** `ls docs/decisions/` and grep for the topic. If an ADR already covers it, update or supersede that one rather than adding a second, competing record.

2. **Confirm it is load-bearing.** Reversing it would touch more than one module, or it rests on an assumption that could prove false, or a reasonable engineer would ask "why is it like this?". If none of those hold, make the choice and skip the ADR.

3. **Write it.** Copy `.claude/skills/decision-record/references/template.md` to `docs/decisions/NNNN-kebab-title.md` using the next free number. Under a page.

4. **Be honest in Consequences.** List what this makes *harder*, not only what it enables. An ADR with no downsides was not a decision.

5. **Status.** If it rests on an unverified assumption (external dependency behaviour, real-corpus size or shape), use `provisional — pending verification` and fill in **Revisit when** with the specific observation that would settle it.

If the decision was made in this conversation, capture the *actual* reasoning that was used — including the constraints the user stated — not a tidied-up rationalisation invented afterwards.
