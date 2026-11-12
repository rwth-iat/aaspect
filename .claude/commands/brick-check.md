---
description: Audit the whole repo against the layer rules and size budgets, then fix what is worth fixing
allowed-tools: Bash(python .claude/hooks/brick_check.py --all)
---

Run the structure audit:

```bash
python .claude/hooks/brick_check.py --all
```

Then report and act:

1. **Blocking findings first** (`query-string-building`, `hardcoded-db-credentials`). Fix them now. Never silence one by adding `# arch-allow:` unless there is a real, written justification, and say out loud when you use it.

2. **Layering findings next** (`layer-direction`, `sibling-adapter`, `pure-layer`). These are design errors, not style. The fix is almost never to move the import — it is usually a missing port method. Consult the `modular-design` skill.

3. **Size findings last** (`file-loc`, `function-loc`, `exports`, `files-per-dir`). For each, decide honestly whether the module really has two jobs. If it does, split it per `modular-design/references/splitting.md`. If it does not, say so and leave it — these are smell detectors, not quotas.

If a threshold is wrong *repeatedly* rather than in one file, that is a signal the threshold itself is wrong. Change it in `.claude/architecture.json`, which is the only place it is defined, and say why.

Summarise: what you fixed, what you deliberately left, and why.
