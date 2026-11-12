---
description: Compare every recorded decision against what the code actually does now, and report the drift
---

Re-examine the project's decisions against its current reality. This is a **read-and-report** pass — do not change code or ADRs until the findings have been shown and the user has picked what to act on.

## 1. Gather

- Read every file in `docs/decisions/`, noting number, title, status, and its **Revisit when** trigger.
- Run `python .claude/hooks/brick_check.py --all` for the current structural picture.
- Look at what the code in `src/aaspect/` actually does for each decision's subject area. Read narrowly — the decision text tells you which module to look at.

## 2. Classify each ADR

| Verdict | Meaning |
|---|---|
| **Holds** | Code matches, assumptions still true. Say so in one line; do not elaborate. |
| **Violated** | Code contradicts an accepted ADR. Either the code is wrong or the ADR is stale — say which you think it is. |
| **Now answerable** | A `provisional` ADR whose **Revisit when** trigger has been met. This is the highest-value category. |
| **Superseded in practice** | Everyone has moved on but the record was never updated. |
| **Obsolete** | The context that motivated it no longer exists. |

## 3. Report

Lead with what needs action. For each item worth acting on: the ADR, what changed, and the specific next step.

Explicitly call out any `provisional` ADR that is **still** unverified while code has been built on the guess — that is the project's main silent-drift risk.

End with a short recommendation on what to do first. Then stop and let the user choose.

## Judgement

Do not manufacture drift to look thorough. "All six decisions hold, nothing to do" is a completely legitimate outcome and should be reported plainly in a few lines rather than padded out.
